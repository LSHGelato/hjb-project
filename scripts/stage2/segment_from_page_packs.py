#!/usr/bin/env python3
"""
HJB Stage 2b - Segment Pages from Page Packs

Purpose:
  - Read page pack manifests and OCR files
  - Apply segmentation heuristics to identify work boundaries
  - Link images to works
  - Output segmentation manifest JSON
  - Ready for operator QA and manual correction

Heuristics:
  - Dividing line detection (separators like ---, ===)
  - Headline detection (short, capitalized, bold-looking lines)
  - Page accumulation (collect consecutive pages into works)
  - Type detection (article, advertisement, plate, etc.)

Output:
  0220_Page_Packs/[container_id]/segmentation/
    segmentation_v2_1.json    # Detected works with boundaries and images

Usage:
  python scripts/stage2/segment_from_page_packs.py --manifest-path 0220_Page_Packs/1/manifest.json
  python scripts/stage2/segment_from_page_packs.py --container-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('segmentation.log'),
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PageSegmentData:
    """Page data for segmentation"""
    page_id: int
    page_index: int
    ocr_text: str
    image_path: str
    ocr_confidence: float = 0.85


@dataclass
class WorkBoundary:
    """Detected work boundary"""
    start_page: int
    end_page: int
    pages: List[int] = field(default_factory=list)
    title: Optional[str] = None
    work_type: str = 'article'
    confidence: float = 0.50
    image_references: List[str] = field(default_factory=list)
    dividing_lines_found: int = 0
    headline_detected: bool = False


# =============================================================================
# Segmentation Heuristics
# =============================================================================

def is_dividing_line(ocr_line: str, threshold: float = 0.7) -> bool:
    """
    Detect horizontal rules (---, ===, etc.) as article separators.

    Args:
        ocr_line: Line of OCR text
        threshold: Minimum ratio of separator chars to line length

    Returns:
        True if line is likely a separator
    """
    stripped = ocr_line.strip()

    # Must have minimum length
    if len(stripped) < 5:
        return False

    # Count separator characters
    separator_chars = (
        stripped.count('-') +
        stripped.count('=') +
        stripped.count('_') +
        stripped.count('*')
    )

    ratio = separator_chars / len(stripped)
    return ratio > threshold


def is_headline(ocr_line: str, max_length: int = 80) -> bool:
    """
    Detect lines likely to be article headlines.

    Heuristics:
    - Short (< 80 chars)
    - All caps or title case
    - Not ending with punctuation (usually periods, commas in body text)
    """
    stripped = ocr_line.strip()

    # Length check
    if not stripped or len(stripped) > max_length:
        return False

    # Case checks
    if stripped.isupper():
        return True
    if stripped.istitle():
        return True

    # Check for all caps words (common in headlines)
    words = stripped.split()
    caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    if len(words) > 0 and caps_words / len(words) > 0.5:
        return True

    return False


def is_byline(ocr_line: str) -> bool:
    """
    Detect lines likely to be bylines (author/attribution).

    Heuristics:
    - Contains "By " or "By:"
    - Or contains author indicators
    """
    stripped = ocr_line.strip().lower()
    return any(x in stripped for x in ['by ', 'by:', 'author:', 'from ', 'correspondent'])


def is_page_break(ocr_line: str) -> bool:
    """
    Detect page break markers (blank lines, page numbers, etc).
    """
    stripped = ocr_line.strip()

    # Empty line
    if not stripped:
        return True

    # Pure numbers (page numbers)
    if stripped.isdigit() and len(stripped) <= 3:
        return True

    # Roman numerals (page numbers)
    if all(c in 'IVXLiv ' for c in stripped) and len(stripped) <= 5:
        return True

    return False


def detect_work_type(page_text: str, page_number: Optional[str] = None) -> str:
    """
    Detect type of work based on OCR text and metadata.

    Returns: 'article', 'advertisement', 'plate', 'index', 'toc', 'blank'
    """
    if not page_text or len(page_text.strip()) < 10:
        return 'blank'

    text_lower = page_text.lower()

    # Advertisement detection
    if any(word in text_lower for word in
           ['advertisement', 'advertise', 'adv.', 'for sale', 'wanted']):
        return 'advertisement'

    # Index/TOC detection
    if any(word in text_lower for word in
           ['index', 'table of contents', 'contents', 'page']):
        return 'index'

    # Default to article
    return 'article'


# =============================================================================
# Main Segmentation Logic
# =============================================================================

def find_work_boundaries(pages_data: List[PageSegmentData]) -> List[WorkBoundary]:
    """
    Given pages with OCR and images, identify work boundaries.

    Uses heuristics to detect article separators, headlines, and accumulate pages.

    Returns:
        List of WorkBoundary objects
    """
    if not pages_data:
        return []

    works: List[WorkBoundary] = []
    current_work: Optional[WorkBoundary] = None

    for page_idx, page_data in enumerate(pages_data):
        ocr_lines = page_data.ocr_text.split('\n')

        for line_idx, line in enumerate(ocr_lines):
            # Skip page breaks
            if is_page_break(line):
                continue

            # Check for dividing line (article break)
            if is_dividing_line(line):
                if current_work:
                    current_work.end_page = page_idx
                    current_work.dividing_lines_found += 1
                    works.append(current_work)
                current_work = None
                logger.debug(f"[Page {page_idx}] Found dividing line")
                continue

            # Check for headline (start of new article)
            if is_headline(line):
                # Save previous work
                if current_work:
                    current_work.end_page = page_idx - 1
                    works.append(current_work)

                # Start new work
                current_work = WorkBoundary(
                    start_page=page_idx,
                    end_page=page_idx,
                    pages=[page_idx],
                    title=line.strip()[:100],  # First 100 chars
                    confidence=0.85,  # High confidence for headline
                    headline_detected=True,
                )
                logger.debug(f"[Page {page_idx}] Found headline: {line[:50]}")
                continue

            # Accumulate text into current work
            if current_work is None:
                current_work = WorkBoundary(
                    start_page=page_idx,
                    end_page=page_idx,
                    pages=[page_idx],
                    title=None,
                    confidence=0.60,  # Lower confidence for no headline
                )
            else:
                if page_idx not in current_work.pages:
                    current_work.pages.append(page_idx)
                    current_work.end_page = page_idx

    # Add final work
    if current_work:
        works.append(current_work)

    # Detect work types
    for work in works:
        # Get combined OCR text for all pages in work
        combined_text = '\n'.join(
            pages_data[page_idx].ocr_text
            for page_idx in work.pages
            if page_idx < len(pages_data)
        )
        work.work_type = detect_work_type(combined_text)

    logger.info(f"Found {len(works)} works from {len(pages_data)} pages")
    return works


def link_images_to_works(
    works: List[WorkBoundary],
    pages_data: List[PageSegmentData]
) -> List[WorkBoundary]:
    """
    For each work, identify which images belong to it.

    Args:
        works: List of WorkBoundary objects
        pages_data: List of PageSegmentData objects

    Returns:
        Updated works with image_references populated
    """
    for work in works:
        image_refs = []
        for page_idx in work.pages:
            if page_idx < len(pages_data):
                page_data = pages_data[page_idx]
                image_refs.append(page_data.image_path)
        work.image_references = image_refs

    return works


def generate_segmentation_manifest(
    works: List[WorkBoundary],
    container_id: int,
    manifest_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate segmentation manifest JSON for review.

    Args:
        works: List of detected WorkBoundary objects
        container_id: Container ID
        manifest_metadata: Original page pack manifest metadata

    Returns:
        Segmentation manifest dictionary
    """
    works_list = []

    for i, work in enumerate(works, 1):
        work_entry = {
            'work_number': i,
            'type': work.work_type,
            'pages': work.pages,
            'page_range': f"{work.start_page}-{work.end_page}",
            'title': work.title,
            'confidence': round(work.confidence, 2),
            'image_count': len(work.image_references),
            'image_references': work.image_references,
            'metadata': {
                'headline_detected': work.headline_detected,
                'dividing_lines_found': work.dividing_lines_found,
            }
        }
        works_list.append(work_entry)

    # Compute statistics
    type_counts = {}
    for work in works:
        work_type = work.work_type
        type_counts[work_type] = type_counts.get(work_type, 0) + 1

    manifest = {
        'manifest_version': '2.1',
        'generation_date': datetime.utcnow().isoformat(),
        'generation_script': 'segment_from_page_packs.py v2.1',
        'container_id': container_id,
        'total_pages': sum(len(w.pages) for w in works),
        'total_works': len(works),
        'works': works_list,
        'statistics': {
            'by_type': type_counts,
            'avg_confidence': round(
                sum(w.confidence for w in works) / len(works), 2
            ) if works else 0.0,
            'total_images': sum(len(w.image_references) for w in works),
        },
        'heuristics_applied': [
            'dividing_line_detection',
            'headline_detection',
            'page_accumulation',
            'work_type_detection'
        ],
        'parameters': {
            'dividing_line_threshold': 0.7,
            'headline_max_length': 80,
            'confidence_high': 0.85,
            'confidence_low': 0.60
        }
    }

    return manifest


def output_segmentation_manifest(
    manifest: Dict[str, Any],
    output_path: Path
) -> bool:
    """
    Save segmentation manifest to JSON file.

    Args:
        manifest: Segmentation manifest dictionary
        output_path: Output file path

    Returns:
        True if successful
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Generated segmentation manifest: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to write manifest: {e}")
        return False


# =============================================================================
# Main Entry Point
# =============================================================================

def process_container_segmentation(
    manifest_path: Path,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Process container for segmentation.

    Args:
        manifest_path: Path to page pack manifest.json
        output_dir: Output directory for segmentation manifest
                   (defaults to parent of manifest_path)

    Returns:
        Result dictionary with status and work count
    """
    result = {
        'status': 'pending',
        'works_detected': 0,
        'manifest_path': str(manifest_path),
        'output_dir': None,
        'error_message': None,
    }

    if not manifest_path.exists():
        result['status'] = 'error'
        result['error_message'] = f"Manifest not found: {manifest_path}"
        logger.error(result['error_message'])
        return result

    try:
        # 1. Load page pack manifest
        logger.info(f"Loading manifest: {manifest_path}")
        with open(manifest_path) as f:
            manifest = json.load(f)

        container_id = manifest['container_id']
        pages_metadata = manifest.get('pages', [])

        logger.info(f"Container {container_id}: {len(pages_metadata)} pages")

        if not output_dir:
            output_dir = manifest_path.parent / 'segmentation'

        # 2. Load page data (OCR + image paths from manifest)
        logger.info("Loading page data...")
        pages_data = []

        for page_entry in pages_metadata:
            try:
                page_id = page_entry['page_id']
                ocr_file = page_entry['ocr_file']
                image_file = page_entry['image_extracted']

                # Load OCR text
                ocr_text = ""
                if Path(ocr_file).exists():
                    try:
                        with open(ocr_file) as f:
                            content = f.read()

                        # Simple text extraction (remove XML/HTML tags)
                        import re
                        ocr_text = re.sub(r'<[^>]+>', ' ', content)
                        ocr_text = ' '.join(ocr_text.split())
                    except Exception as e:
                        logger.warning(f"Failed to read OCR {ocr_file}: {e}")
                        ocr_text = ""

                pages_data.append(PageSegmentData(
                    page_id=page_id,
                    page_index=page_entry['page_index'],
                    ocr_text=ocr_text,
                    image_path=image_file,
                    ocr_confidence=page_entry.get('ocr_confidence', 0.85)
                ))

            except Exception as e:
                logger.warning(f"Failed to load page {page_entry.get('page_id')}: {e}")

        if not pages_data:
            result['status'] = 'error'
            result['error_message'] = 'Could not load page data from manifest'
            return result

        logger.info(f"Loaded {len(pages_data)} pages")

        # 3. Apply segmentation heuristics
        logger.info("Detecting work boundaries...")
        works = find_work_boundaries(pages_data)

        # 4. Link images to works
        logger.info("Linking images to works...")
        works = link_images_to_works(works, pages_data)

        # 5. Generate segmentation manifest
        logger.info("Generating segmentation manifest...")
        seg_manifest = generate_segmentation_manifest(
            works,
            container_id,
            manifest
        )

        # 6. Save segmentation manifest
        seg_output_path = output_dir / 'segmentation_v2_1.json'
        if output_segmentation_manifest(seg_manifest, seg_output_path):
            result['output_dir'] = str(output_dir)
        else:
            result['status'] = 'error'
            result['error_message'] = 'Failed to write segmentation manifest'
            return result

        # 7. Log results
        result['status'] = 'success'
        result['works_detected'] = len(works)

        logger.info(f"\n[RESULTS] Container {container_id}")
        logger.info(f"  Works detected: {len(works)}")
        logger.info(f"  By type: {seg_manifest['statistics']['by_type']}")
        logger.info(f"  Average confidence: {seg_manifest['statistics']['avg_confidence']}")

        for i, work in enumerate(works, 1):
            logger.info(f"    [{i}] {work.work_type.upper()}: "
                       f"pages {work.pages}, confidence {work.confidence:.2f}")

        return result

    except Exception as e:
        logger.exception(f"Segmentation failed: {e}")
        result['status'] = 'error'
        result['error_message'] = str(e)
        return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Segment pages from page packs using heuristics'
    )
    parser.add_argument(
        '--manifest-path',
        type=Path,
        help='Path to page pack manifest.json'
    )
    parser.add_argument(
        '--container-id',
        type=int,
        help='Container ID (will look for manifest at 0220_Page_Packs/{id}/manifest.json)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory for segmentation results'
    )

    args = parser.parse_args()

    # Determine manifest path
    if args.manifest_path:
        manifest_path = args.manifest_path
    elif args.container_id:
        manifest_path = Path('0220_Page_Packs') / str(args.container_id) / 'manifest.json'
    else:
        parser.print_help()
        return 1

    # Process
    result = process_container_segmentation(manifest_path, args.output_dir)

    if result['status'] == 'success':
        logger.info(f"\n[SUCCESS] Segmentation complete: {result['works_detected']} works detected")
        logger.info(f"Output: {result['output_dir']}")
        return 0
    else:
        logger.error(f"\n[FAILED] {result['error_message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
