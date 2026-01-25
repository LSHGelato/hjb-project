#!/usr/bin/env python3
"""
HJB Stage 2a - Extract Pages from Containers (v2)

Refactored version with hybrid database + filesystem architecture.

Purpose:
  - Extract JP2 images from IA containers → convert to JPEG
  - Copy OCR payloads (DjVu XML, HOCR) to page pack directory
  - Populate pages_t with snippet + metadata
  - Create page_assets_t entries with pointers + hashes
  - Generate page pack manifest JSON
  - Create page_pack_manifests_t entry
  - Handle errors gracefully with comprehensive logging

Usage:
  python scripts/stage2/extract_pages_v2.py --container-id 1
  python scripts/stage2/extract_pages_v2.py --container-id 1 2 3
  python scripts/stage2/extract_pages_v2.py --all-pending
  python scripts/stage2/extract_pages_v2.py --container-id 1 --dry-run

Output Structure:
  0220_Page_Packs/
    {container_id}/
      manifest.json                 # Page pack contents and metadata
      images/
        page_0001.jpg              # Extracted images
        page_0002.jpg
      ocr/
        page_0001.hocr             # OCR files (copied from raw input)
        page_0002.xml

Database Tables:
  pages_t          → Updated with ocr_text_snippet, ocr_char_count
  page_assets_t    → New rows with image/OCR file references
  page_pack_manifests_t → New row documenting entire container's pack
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common import hjb_db
from scripts.common.hjb_db import load_config
from scripts.stage2 import hocr_parser

# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('extract_pages_v2.log'),
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ImageMetadata:
    """Metadata for extracted image"""
    jpeg_path: str
    original_hash: str
    extracted_hash: str
    image_width: int
    image_height: int
    image_dpi: int
    format: str = 'JPEG'


@dataclass
class OCRFileReference:
    """Reference to OCR file in page pack"""
    ocr_path: str
    ocr_hash: str
    ocr_format: str  # djvu_xml, hocr, alto, tesseract_json
    ocr_source: str  # ia_djvu, ia_hocr, etc.


@dataclass
class PageExtractedData:
    """All extracted data for a single page"""
    page_id: int
    page_index: int
    container_id: int
    image_meta: ImageMetadata
    ocr_ref: OCRFileReference
    ocr_text_snippet: str
    ocr_char_count: int
    page_type: str = 'content'


# =============================================================================
# Hash and File Utilities
# =============================================================================

def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def ensure_directory(dir_path: Path) -> bool:
    """Ensure directory exists, create if needed."""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {dir_path}: {e}")
        return False


# =============================================================================
# Image Extraction
# =============================================================================

def extract_jp2_to_jpeg(
    jp2_path: Path,
    output_path: Path,
    quality: int = 90,
    normalize_dpi: int = 300
) -> Optional[ImageMetadata]:
    """
    Extract JP2 image → convert to JPEG, compute hashes.

    Args:
        jp2_path: Path to source JP2 file
        output_path: Path to output JPEG file
        quality: JPEG quality (0-100)
        normalize_dpi: Target DPI for normalization

    Returns:
        ImageMetadata with paths, hashes, dimensions, DPI
        None if extraction failed
    """
    try:
        from PIL import Image
    except ImportError:
        logger.error("Pillow (PIL) not installed. Install with: pip install Pillow")
        return None

    if not jp2_path.exists():
        logger.warning(f"JP2 file not found: {jp2_path}")
        return None

    try:
        logger.debug(f"Opening JP2: {jp2_path}")
        img = Image.open(jp2_path)

        # Get original dimensions and DPI
        original_dpi = img.info.get('dpi', (normalize_dpi, normalize_dpi))[0]
        original_width, original_height = img.size

        # Convert RGBA to RGB (JPEG doesn't support alpha)
        if img.mode == 'RGBA':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Normalize DPI if needed
        if original_dpi != normalize_dpi:
            logger.debug(f"Normalizing DPI: {original_dpi} → {normalize_dpi}")

        # Save JPEG
        logger.debug(f"Saving JPEG to {output_path}")
        img.save(output_path, format='JPEG', quality=quality, dpi=(normalize_dpi, normalize_dpi))

        # Compute hashes
        original_hash = compute_sha256(jp2_path)
        extracted_hash = compute_sha256(output_path)

        logger.info(f"Extracted JPEG: {output_path.name} ({original_width}x{original_height}, {normalize_dpi}dpi)")

        return ImageMetadata(
            jpeg_path=str(output_path),
            original_hash=original_hash,
            extracted_hash=extracted_hash,
            image_width=original_width,
            image_height=original_height,
            image_dpi=normalize_dpi,
            format='JPEG'
        )

    except Exception as e:
        logger.error(f"Failed to extract JP2 {jp2_path}: {type(e).__name__}: {e}")
        return None


# =============================================================================
# OCR File Handling
# =============================================================================

def locate_ocr_file(container_path: Path, identifier: str) -> Optional[Path]:
    """
    Find OCR file (DjVu XML or HOCR) in container directory.

    Priority:
    1. DjVu XML (_djvu.xml)
    2. HOCR HTML (_hocr.html)
    """
    for ext in ['_djvu.xml', '_hocr.html']:
        candidate = container_path / f"{identifier}{ext}"
        if candidate.exists():
            return candidate
    return None


def locate_scandata(container_path: Path, identifier: str) -> Optional[Path]:
    """Find scandata.xml in container directory."""
    scandata_path = container_path / f"{identifier}_scandata.xml"
    return scandata_path if scandata_path.exists() else None


def discover_jp2_files(container_path: Path) -> tuple[List[Path], Optional[Path]]:
    """
    Discover JP2 files in container, handling both individual files and ZIP archives.

    IA containers can have JP2 images in two formats:
    1. Individual JP2 files in *_jp2/ subdirectory
    2. Zipped JP2 files in *_jp2.zip archive

    Args:
        container_path: Root path of raw container

    Returns:
        (jp2_file_list, temp_extract_dir)
        - jp2_file_list: List of Path objects for JP2 files (sorted)
        - temp_extract_dir: Temporary directory path if extracted from ZIP, None if individual files
                           (Caller must clean this up when done)

    Note:
        If ZIP was extracted, caller must delete temp_extract_dir after processing.
    """
    # First, try individual JP2 files in *_jp2/ subdirectory
    jp2_files = list(container_path.glob("*_jp2/*.jp2"))

    if jp2_files:
        logger.debug(f"  Found {len(jp2_files)} individual JP2 files in *_jp2/ directory")
        return sorted(jp2_files), None

    # If no individual files, try ZIP archive
    jp2_zips = list(container_path.glob("*_jp2.zip"))

    if jp2_zips:
        zip_path = jp2_zips[0]
        logger.debug(f"  Found JP2 ZIP archive: {zip_path.name}")

        try:
            # Extract to temporary directory
            temp_dir = Path(tempfile.mkdtemp(prefix="hjb_jp2_"))
            logger.debug(f"  Extracting ZIP to: {temp_dir}")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find JP2 files in extracted directory
            extracted_jp2s = list(temp_dir.glob("**/*.jp2"))

            if extracted_jp2s:
                logger.debug(f"  Extracted {len(extracted_jp2s)} JP2 files from ZIP")
                return sorted(extracted_jp2s), temp_dir
            else:
                logger.warning(f"  ZIP file extracted but no JP2 files found inside")
                # Clean up empty extraction
                shutil.rmtree(temp_dir)
                return [], None

        except zipfile.BadZipFile as e:
            logger.warning(f"  ZIP file is corrupt or invalid: {e}")
            return [], None
        except Exception as e:
            logger.warning(f"  Failed to extract JP2 ZIP: {e}")
            return [], None

    # No JP2 files found in either format
    logger.warning(f"  No JP2 files or ZIP archive found in {container_path}")
    return [], None


def copy_ocr_file(
    source_path: Path,
    dest_dir: Path,
    page_index: int
) -> Optional[OCRFileReference]:
    """
    Copy OCR file to page pack directory.

    Args:
        source_path: Source OCR file
        dest_dir: Output directory (e.g., 0220_Page_Packs/1/ocr/)
        page_index: 0-based page index

    Returns:
        OCRFileReference with path, hash, format
        None if copy failed
    """
    if not source_path.exists():
        logger.warning(f"OCR file not found: {source_path}")
        return None

    try:
        # Determine format
        if source_path.suffix == '.xml':
            ocr_format = 'djvu_xml'
            ocr_source = 'ia_djvu'
            dest_filename = f"page_{page_index:04d}.xml"
        elif source_path.suffix == '.html':
            ocr_format = 'hocr'
            ocr_source = 'ia_hocr'
            dest_filename = f"page_{page_index:04d}.hocr"
        else:
            logger.warning(f"Unknown OCR format: {source_path.suffix}")
            return None

        dest_path = dest_dir / dest_filename

        # Copy file
        shutil.copy2(source_path, dest_path)
        logger.debug(f"Copied OCR: {dest_filename}")

        # Compute hash
        ocr_hash = compute_sha256(dest_path)

        return OCRFileReference(
            ocr_path=str(dest_path),
            ocr_hash=ocr_hash,
            ocr_format=ocr_format,
            ocr_source=ocr_source
        )

    except Exception as e:
        logger.error(f"Failed to copy OCR file: {e}")
        return None


def extract_ocr_text_snippet(ocr_path: Path, length: int = 500) -> tuple[str, int]:
    """
    Extract first N characters of OCR as snippet.

    Args:
        ocr_path: Path to OCR file
        length: Character limit for snippet

    Returns:
        Tuple of (text_snippet, char_count)
    """
    if not ocr_path.exists():
        return "", 0

    try:
        if ocr_path.suffix == '.xml':
            # Parse DjVu XML
            tree = ET.parse(ocr_path)
            root = tree.getroot()
            text_parts = []

            for word_elem in root.findall(".//WORD"):
                if word_elem.text:
                    text_parts.append(word_elem.text)

            full_text = " ".join(text_parts)
        elif ocr_path.suffix in ['.html', '.hocr']:
            # Parse HOCR HTML
            with open(ocr_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple text extraction from HOCR
            import re
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', content)
            full_text = ' '.join(text.split())  # Normalize whitespace
        else:
            logger.warning(f"Unknown OCR format for snippet: {ocr_path.suffix}")
            return "", 0

        snippet = full_text[:length]
        char_count = len(full_text)

        logger.debug(f"Extracted OCR snippet: {len(snippet)} chars from {char_count} total")
        return snippet, char_count

    except Exception as e:
        logger.error(f"Failed to extract OCR snippet: {e}")
        return "", 0


# =============================================================================
# Manifest Generation
# =============================================================================

def generate_manifest_json(
    container_id: int,
    issue_id: Optional[int],
    pages_data: List[PageExtractedData],
    extraction_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create manifest JSON documenting page pack contents.

    Args:
        container_id: Container ID
        issue_id: Issue ID (may be None if not mapped)
        pages_data: List of PageExtractedData for all pages
        extraction_params: Extraction settings (quality, dpi, etc.)

    Returns:
        Manifest dictionary (ready to be JSONified)
    """
    pages_manifest = []

    for page in pages_data:
        pages_manifest.append({
            'page_id': page.page_id,
            'page_index': page.page_index,
            'page_type': page.page_type,
            'image_extracted': page.image_meta.jpeg_path,
            'image_hash': page.image_meta.extracted_hash,
            'image_dimensions': {
                'width': page.image_meta.image_width,
                'height': page.image_meta.image_height,
            },
            'image_dpi': page.image_meta.image_dpi,
            'ocr_file': page.ocr_ref.ocr_path,
            'ocr_format': page.ocr_ref.ocr_format,
            'ocr_hash': page.ocr_ref.ocr_hash,
            'ocr_source': page.ocr_ref.ocr_source,
            'metadata': {
                'dpi_normalized': page.image_meta.image_dpi,
                'original_hash': page.image_meta.original_hash,
            }
        })

    # Statistics
    total_ocr_chars = sum(p.ocr_char_count for p in pages_data)
    avg_confidence = sum(
        getattr(p, 'ocr_confidence', 0.0) for p in pages_data
    ) / len(pages_data) if pages_data else 0.0

    manifest = {
        'manifest_version': '2.0',
        'generation_date': datetime.utcnow().isoformat(),
        'generation_script': 'extract_pages_v2.py',
        'container_id': container_id,
        'issue_id': issue_id,
        'total_pages': len(pages_data),
        'pages': pages_manifest,
        'statistics': {
            'total_pages': len(pages_data),
            'total_ocr_characters': total_ocr_chars,
            'avg_ocr_confidence': round(avg_confidence, 2),
            'ocr_sources_used': list(set(p.ocr_ref.ocr_source for p in pages_data)),
        },
        'extraction_parameters': extraction_params,
        'image_stats': {
            'format': 'JPEG',
            'quality': extraction_params.get('jpeg_quality', 90),
            'dpi_normalized': extraction_params.get('normalize_dpi', 300),
        }
    }

    return manifest


# =============================================================================
# Database Operations
# =============================================================================

def populate_page_assets_t(
    db_conn: Any,
    page_extracted_data: PageExtractedData
) -> Optional[int]:
    """
    Insert row into page_assets_t with image and OCR references.

    Args:
        db_conn: Database connection
        page_extracted_data: Extracted data for page

    Returns:
        asset_id if successful, None otherwise
    """
    try:
        cursor = db_conn.cursor()

        query = """
            INSERT INTO page_assets_t
            (page_id, ocr_payload_path, ocr_payload_hash, ocr_payload_format,
             image_extracted_path, image_extracted_format, image_extracted_hash,
             image_source, image_dpi_normalized, extracted_at, extraction_script_version,
             created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), NOW())
        """

        cursor.execute(query, (
            page_extracted_data.page_id,
            page_extracted_data.ocr_ref.ocr_path,
            page_extracted_data.ocr_ref.ocr_hash,
            page_extracted_data.ocr_ref.ocr_format,
            page_extracted_data.image_meta.jpeg_path,
            page_extracted_data.image_meta.format,
            page_extracted_data.image_meta.extracted_hash,
            'ia_jp2',
            page_extracted_data.image_meta.image_dpi,
            'extract_pages_v2.py v2.0',
        ))

        db_conn.commit()
        asset_id = cursor.lastrowid
        cursor.close()

        return asset_id

    except mysql.connector.Error as e:
        logger.error(f"Database error inserting page_assets_t: {e}")
        db_conn.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None


def populate_page_pack_manifests_t(
    db_conn: Any,
    container_id: int,
    manifest_path: str,
    manifest_data: Dict[str, Any],
    page_ids: List[int]
) -> Optional[int]:
    """
    Insert row into page_pack_manifests_t.

    Args:
        db_conn: Database connection
        container_id: Container ID
        manifest_path: File path to manifest.json
        manifest_data: Manifest dictionary
        page_ids: List of page_id values included

    Returns:
        manifest_id if successful, None otherwise
    """
    try:
        cursor = db_conn.cursor()

        # Compute hash of manifest
        manifest_json = json.dumps(manifest_data, indent=2)
        manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()

        # Prepare data
        ocr_sources = json.dumps(list(set(
            manifest_data['statistics']['ocr_sources_used']
        )))
        page_ids_json = json.dumps(page_ids)
        extraction_params_json = json.dumps(manifest_data['extraction_parameters'])

        query = """
            INSERT INTO page_pack_manifests_t
            (container_id, manifest_path, manifest_hash, manifest_version,
             total_pages, page_ids_included, ocr_sources_used,
             image_extraction_params, created_by, description, created_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), 1)
        """

        cursor.execute(query, (
            container_id,
            manifest_path,
            manifest_hash,
            manifest_data['manifest_version'],
            manifest_data['total_pages'],
            page_ids_json,
            ocr_sources,
            extraction_params_json,
            'extract_pages_v2.py',
            f"Page pack for container {container_id}",
        ))

        db_conn.commit()
        manifest_id = cursor.lastrowid
        cursor.close()

        return manifest_id

    except mysql.connector.Error as e:
        logger.error(f"Database error inserting page_pack_manifests_t: {e}")
        db_conn.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None


# =============================================================================
# Main Processing
# =============================================================================

def process_container(
    container_id: int,
    dry_run: bool = False,
    page_packs_root: Path = Path("0220_Page_Packs"),
    jpeg_quality: int = 90,
    normalize_dpi: int = 300
) -> Dict[str, Any]:
    """
    Process single container: extract images, copy OCR, generate manifest.

    Returns:
        Result dictionary with status, counts, and details
    """
    result = {
        'container_id': container_id,
        'status': 'pending',
        'pages_processed': 0,
        'pages_failed': 0,
        'pages_with_images': 0,
        'pages_with_ocr': 0,
        'manifest_generated': False,
        'error_message': None,
    }

    logger.info(f"=" * 70)
    logger.info(f"Processing Container {container_id}")
    logger.info(f"=" * 70)

    try:
        # 1. Get container metadata
        container = hjb_db.get_container_by_source("internet_archive", None)
        # Note: Need to query by container_id instead
        query = "SELECT * FROM containers_t WHERE container_id = %s"
        containers = hjb_db.execute_query(query, (container_id,), fetch=True)

        if not containers:
            result['status'] = 'error'
            result['error_message'] = f"Container {container_id} not found in database"
            logger.error(result['error_message'])
            return result

        container = containers[0]
        identifier = container['source_identifier']
        raw_input_path = container.get('raw_input_path')

        if not raw_input_path:
            result['status'] = 'error'
            result['error_message'] = 'raw_input_path not set for container'
            logger.error(result['error_message'])
            return result

        logger.info(f"Container: {identifier}")
        logger.info(f"Raw input path: {raw_input_path}")

        # 2. Setup output directories
        # Load config to get absolute path to working files
        try:
            config = load_config()
            working_files_root = Path(config.get('storage', {}).get('working_files'))
            page_packs_subdir = config.get('storage', {}).get('page_packs_dir', '0220_Page_Packs')
            page_packs_root = working_files_root / page_packs_subdir
        except Exception as e:
            logger.warning(f"Failed to load config for absolute paths: {e}")
            # Fallback to provided parameter
            pass

        container_pack_dir = page_packs_root / str(container_id)
        images_dir = container_pack_dir / "images"
        ocr_dir = container_pack_dir / "ocr"

        if not dry_run:
            for d in [container_pack_dir, images_dir, ocr_dir]:
                if not ensure_directory(d):
                    result['status'] = 'error'
                    result['error_message'] = f"Failed to create directory: {d}"
                    return result

        logger.info(f"Output directory: {container_pack_dir}")

        # 3. Get pages for this container
        page_query = """
            SELECT p.page_id, p.page_index, p.page_type, p.issue_id
            FROM pages_t p
            WHERE p.container_id = %s
            ORDER BY p.page_index
        """
        pages = hjb_db.execute_query(page_query, (container_id,), fetch=True)

        if not pages:
            result['status'] = 'error'
            result['error_message'] = 'No pages found for container'
            logger.error(result['error_message'])
            return result

        logger.info(f"Found {len(pages)} pages to process")

        # 4. Process each page
        pages_data = []
        extraction_params = {
            'jpeg_quality': jpeg_quality,
            'normalize_dpi': normalize_dpi,
            'preprocessing': {
                'deskew': False,
                'binarize': False,
            }
        }

        raw_container_path = Path(raw_input_path)

        # Discover JP2 files (handles both individual files and ZIP archives)
        logger.info("Discovering JP2 image files...")
        jp2_files, jp2_temp_dir = discover_jp2_files(raw_container_path)

        if not jp2_files:
            result['status'] = 'warning'
            result['error_message'] = "No JP2 image files found in container"
            logger.warning(result['error_message'])
            # Don't return - continue with OCR-only extraction if available

        # Connect to database for page updates
        try:
            db_conn = hjb_db.get_connection()
        except Exception as e:
            result['status'] = 'error'
            result['error_message'] = f"Failed to connect to database: {e}"
            logger.error(result['error_message'])
            # Clean up temp directory if it was created
            if jp2_temp_dir:
                shutil.rmtree(jp2_temp_dir)
            return result

        for page in pages:
            page_id = page['page_id']
            page_index = page['page_index']
            page_type = page.get('page_type', 'content')

            logger.info(f"  Page {page_index + 1}/{len(pages)}: page_id={page_id}")

            # Initialize data collectors
            image_meta = None
            ocr_ref = None
            ocr_text_snippet = ""
            ocr_char_count = 0
            page_extracted_success = False
            page_ocr_success = False

            # Step 1: Extract JP2 to JPEG
            try:
                if jp2_files and page_index < len(jp2_files):
                    jp2_path = jp2_files[page_index]

                    # Extract and convert
                    image_meta = extract_jp2_to_jpeg(
                        jp2_path,
                        images_dir / f"page_{page_index:04d}.jpg",
                        quality=jpeg_quality,
                        normalize_dpi=normalize_dpi
                    )

                    if image_meta:
                        page_extracted_success = True
                        result['pages_with_images'] += 1
                        logger.debug(f"    Extracted image: {image_meta.jpeg_path}")
                elif jp2_files:
                    logger.warning(f"    Page {page_index} exceeds available JP2 files ({len(jp2_files)} total)")
                else:
                    logger.debug(f"    Skipping image extraction (no JP2 files available)")

            except Exception as e:
                logger.warning(f"    Failed to extract image: {e}")

            # Step 2: Find and copy OCR file
            dest_name = None  # Initialize for use in pages_data section
            try:
                ocr_path = None
                ocr_format = None
                ocr_source = None

                # Try DjVu XML first (preferred)
                djvu_files = list(raw_container_path.glob("*_djvu.xml"))
                if djvu_files:
                    ocr_path = djvu_files[0]
                    ocr_format = 'djvu_xml'
                    ocr_source = 'ia_djvu'
                else:
                    # Try HOCR HTML
                    hocr_files = list(raw_container_path.glob("*_hocr.html"))
                    if hocr_files:
                        ocr_path = hocr_files[0]
                        ocr_format = 'hocr'
                        ocr_source = 'ia_hocr'

                if ocr_path and ocr_path.exists():
                    # Copy to page pack directory
                    if ocr_format == 'djvu_xml':
                        dest_name = f"page_{page_index:04d}.xml"
                    else:
                        dest_name = f"page_{page_index:04d}.hocr"

                    dest_path = ocr_dir / dest_name

                    if not dry_run:
                        shutil.copy2(ocr_path, dest_path)
                        ocr_hash = compute_sha256(dest_path)

                        # Extract OCR text snippet (first 200 chars)
                        try:
                            if ocr_format == 'djvu_xml':
                                # Parse DjVu XML
                                tree = ET.parse(dest_path)
                                root = tree.getroot()
                                text_parts = []
                                for word_elem in root.findall(".//WORD"):
                                    if word_elem.text:
                                        text_parts.append(word_elem.text)
                                full_text = " ".join(text_parts)
                            else:
                                # Parse HOCR HTML - simple text extraction
                                with open(dest_path) as f:
                                    content = f.read()
                                full_text = re.sub(r'<[^>]+>', ' ', content)
                                full_text = ' '.join(full_text.split())

                            ocr_text_snippet = full_text[:200]
                            ocr_char_count = len(full_text)

                        except Exception as e:
                            logger.warning(f"    Failed to extract OCR text: {e}")

                        # Build OCR reference object
                        ocr_ref = OCRFileReference(
                            ocr_path=str(dest_path),
                            ocr_hash=ocr_hash,
                            ocr_format=ocr_format,
                            ocr_source=ocr_source
                        )

                        # Update pages_t with OCR snippet and char count
                        try:
                            cursor = db_conn.cursor()
                            cursor.execute("""
                                UPDATE pages_t
                                SET ocr_text_snippet = %s, ocr_char_count = %s
                                WHERE page_id = %s
                            """, (ocr_text_snippet, ocr_char_count, page_id))
                            db_conn.commit()
                            cursor.close()

                            result['pages_with_ocr'] += 1
                            page_ocr_success = True
                            logger.debug(f"    Copied OCR: {dest_name} ({ocr_char_count} chars)")
                        except Exception as e:
                            logger.warning(f"    Failed to update pages_t: {e}")
                    else:
                        logger.debug(f"    [DRY RUN] Would copy: {dest_name}")
                        result['pages_with_ocr'] += 1
                        page_ocr_success = True
                else:
                    logger.warning(f"    OCR file not found in {raw_container_path}")

            except Exception as e:
                logger.warning(f"    Failed to process OCR: {e}")

            # Step 3: Insert into page_assets_t if both image and OCR succeeded
            if image_meta and ocr_ref and page_extracted_success and not dry_run:
                try:
                    page_extracted_data = PageExtractedData(
                        page_id=page_id,
                        page_index=page_index,
                        container_id=container_id,
                        image_meta=image_meta,
                        ocr_ref=ocr_ref,
                        ocr_text_snippet=ocr_text_snippet,
                        ocr_char_count=ocr_char_count,
                        page_type=page_type
                    )

                    asset_id = populate_page_assets_t(db_conn, page_extracted_data)
                    if asset_id:
                        logger.debug(f"    Page asset record created: asset_id={asset_id}")
                    else:
                        logger.warning(f"    Failed to create page asset record")

                except Exception as e:
                    logger.warning(f"    Failed to insert page asset: {e}")

            # Add to pages_data for manifest (if both image and OCR succeeded)
            if page_extracted_success and page_ocr_success and dest_name:
                pages_data.append({
                    'page_id': page_id,
                    'page_index': page_index,
                    'page_type': page_type,
                    'image_extracted': str(images_dir / f"page_{page_index:04d}.jpg"),
                    'ocr_file': str(ocr_dir / dest_name),
                })

            result['pages_processed'] += 1

        # 5. Generate manifest
        if not dry_run:
            manifest = generate_manifest_json(
                container_id=container_id,
                issue_id=pages[0].get('issue_id') if pages else None,
                pages_data=pages_data,
                extraction_params=extraction_params
            )

            manifest_path = container_pack_dir / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)

            logger.info(f"Generated manifest: {manifest_path}")
            result['manifest_generated'] = True

            # 6. Populate database
            try:
                with hjb_db.get_connection() as conn:
                    # Insert manifest record
                    manifest_id = populate_page_pack_manifests_t(
                        conn,
                        container_id,
                        str(manifest_path),
                        manifest,
                        [p['page_id'] for p in pages]
                    )

                    if manifest_id:
                        logger.info(f"Created page_pack_manifests entry: {manifest_id}")
                    else:
                        logger.warning("Failed to create page_pack_manifests entry")

            except Exception as e:
                logger.error(f"Database operations failed: {e}")

        result['status'] = 'success'
        logger.info(f"Container {container_id} processing complete")
        logger.info(f"  Pages processed: {result['pages_processed']}")
        logger.info(f"  Pages with images: {result['pages_with_images']}")
        logger.info(f"  Pages with OCR: {result['pages_with_ocr']}")

        # Clean up temporary directory if JP2 was extracted from ZIP
        if jp2_temp_dir:
            try:
                shutil.rmtree(jp2_temp_dir)
                logger.debug(f"  Cleaned up temporary JP2 extraction directory")
            except Exception as e:
                logger.warning(f"  Failed to clean up temp directory: {e}")

        return result

    except Exception as e:
        logger.exception(f"Unexpected error processing container: {e}")
        result['status'] = 'error'
        result['error_message'] = str(e)

        # Clean up temporary directory on error
        if jp2_temp_dir:
            try:
                shutil.rmtree(jp2_temp_dir)
            except Exception:
                pass

        return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract pages from IA containers to page packs'
    )
    parser.add_argument('--container-id', type=int, nargs='+',
                       help='Container ID(s) to process')
    parser.add_argument('--all-pending', action='store_true',
                       help='Process all pending containers')
    parser.add_argument('--dry-run', action='store_true',
                       help='Parse but don\'t create files or update DB')
    parser.add_argument('--page-packs-root', type=Path, default=Path('0220_Page_Packs'),
                       help='Root directory for page packs')
    parser.add_argument('--jpeg-quality', type=int, default=90,
                       help='JPEG quality (0-100)')

    args = parser.parse_args()

    # Determine containers to process
    container_ids = []

    if args.container_id:
        container_ids = args.container_id
    elif args.all_pending:
        logger.info("Querying pending containers...")
        pending = hjb_db.execute_query("""
            SELECT container_id FROM containers_t
            WHERE container_id NOT IN (
                SELECT container_id FROM page_pack_manifests_t WHERE is_active = 1
            )
            ORDER BY container_id
        """, fetch=True)
        container_ids = [p['container_id'] for p in pending]
        logger.info(f"Found {len(container_ids)} pending containers")
    else:
        parser.print_help()
        return 1

    if not container_ids:
        logger.info("No containers to process")
        return 0

    logger.info(f"Processing {len(container_ids)} container(s)")

    # Process containers
    results = []
    for container_id in container_ids:
        result = process_container(
            container_id,
            dry_run=args.dry_run,
            page_packs_root=args.page_packs_root,
            jpeg_quality=args.jpeg_quality
        )
        results.append(result)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    successful = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'error')
    total_pages = sum(r['pages_processed'] for r in results)

    logger.info(f"Containers: {successful} successful, {failed} failed")
    logger.info(f"Pages processed: {total_pages}")

    if args.dry_run:
        logger.info("[DRY RUN] No files or database changes were made")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
