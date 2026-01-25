#!/usr/bin/env python3
"""
HJB QA - Generate Quality Control Reports

Purpose:
  - Generate HTML and CSV reports for operator QA
  - Show detected works with page ranges and images
  - Summary statistics (articles, ads, plates, etc.)
  - Confidence scores and segmentation details
  - Quick spot-checks for operator review

Output:
  0220_Page_Packs/[container_id]/qa/
    qc_report.html    # Interactive HTML report
    qc_report.csv     # Spreadsheet for annotations

Usage:
  python scripts/qa/generate_qc_report.py --container-id 1
  python scripts/qa/generate_qc_report.py --manifest-path 0220_Page_Packs/1/manifest.json
  python scripts/qa/generate_qc_report.py --segmentation-path 0220_Page_Packs/1/segmentation/segmentation_v2_1.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('qc_report.log'),
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# HTML Report Generation
# =============================================================================

def generate_html_report(
    container_id: int,
    manifest_data: Dict[str, Any],
    segmentation_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate HTML QC report with work summaries.

    Args:
        container_id: Container ID
        manifest_data: Page pack manifest dictionary
        segmentation_data: Optional segmentation manifest

    Returns:
        HTML string
    """
    total_pages = manifest_data.get('total_pages', 0)
    works = segmentation_data.get('works', []) if segmentation_data else []

    # Type counts
    type_counts = {}
    for work in works:
        work_type = work.get('type', 'unknown')
        type_counts[work_type] = type_counts.get(work_type, 0) + 1

    # Average confidence
    avg_confidence = (
        segmentation_data.get('statistics', {}).get('avg_confidence', 0.0)
        if segmentation_data else 0.0
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QC Report - Container {container_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
        h1 {{
            margin: 0 0 10px 0;
        }}
        .info {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background-color: white;
            padding: 20px;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #3498db;
        }}
        .stat-card.articles {{
            border-left-color: #3498db;
        }}
        .stat-card.advertisements {{
            border-left-color: #e74c3c;
        }}
        .stat-card.plates {{
            border-left-color: #f39c12;
        }}
        .stat-card .label {{
            font-size: 12px;
            text-transform: uppercase;
            color: #7f8c8d;
            margin-bottom: 10px;
        }}
        .stat-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .table-container {{
            background-color: white;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .type-article {{
            background-color: #d5e8f7;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
            color: #2c3e50;
        }}
        .type-advertisement {{
            background-color: #fadbd8;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
            color: #a93226;
        }}
        .type-plate {{
            background-color: #fdebd0;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
            color: #922b0e;
        }}
        .confidence {{
            display: inline-block;
            width: 60px;
            height: 20px;
            background: linear-gradient(to right, #27ae60 0%, #f39c12 50%, #e74c3c 100%);
            border-radius: 3px;
            color: white;
            text-align: center;
            font-size: 12px;
            line-height: 20px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            font-size: 12px;
            color: #7f8c8d;
        }}
        h2 {{
            color: #2c3e50;
            margin-top: 30px;
            margin-bottom: 15px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>QC Report - Container {container_id}</h1>
        <div class="info">
            <strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
            <strong>Pages:</strong> {total_pages} | <strong>Works:</strong> {len(works)}
        </div>
    </div>

    <h2>Summary Statistics</h2>
    <div class="stats">
        <div class="stat-card articles">
            <div class="label">Articles</div>
            <div class="value">{type_counts.get('article', 0)}</div>
        </div>
        <div class="stat-card advertisements">
            <div class="label">Advertisements</div>
            <div class="value">{type_counts.get('advertisement', 0)}</div>
        </div>
        <div class="stat-card plates">
            <div class="label">Plates</div>
            <div class="value">{type_counts.get('plate', 0)}</div>
        </div>
        <div class="stat-card">
            <div class="label">Average Confidence</div>
            <div class="value">{avg_confidence:.2f}</div>
        </div>
    </div>

    <h2>Detected Works</h2>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Type</th>
                    <th>Pages</th>
                    <th>Title</th>
                    <th>Confidence</th>
                    <th>Images</th>
                    <th>Notes</th>
                </tr>
            </thead>
            <tbody>
"""

    for work in works:
        work_number = work['work_number']
        work_type = work['type']
        pages_str = ', '.join(str(p) for p in work['pages'])
        title = work.get('title', '(No title)')[:60]
        confidence = work['confidence']
        image_count = work.get('image_count', 0)
        headline = 'Headline detected' if work.get('metadata', {}).get('headline_detected') else ''

        type_class = f'type-{work_type}'
        confidence_pct = int(confidence * 100)

        html += f"""
                <tr>
                    <td>{work_number}</td>
                    <td><span class="{type_class}">{work_type.upper()}</span></td>
                    <td>{pages_str}</td>
                    <td>{title}</td>
                    <td><span class="confidence">{confidence_pct}%</span></td>
                    <td>{image_count}</td>
                    <td>{headline}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
    </div>

    <div class="footer">
        <p>This report was auto-generated. Review and validate results before committing to database.</p>
        <p>
            For corrections: Use <code>scripts/qa/apply_operator_corrections.py</code><br>
            For issues: Contact Michael or Claude Code
        </p>
    </div>
</body>
</html>
"""

    return html


def generate_csv_report(works: List[Dict[str, Any]]) -> List[List[str]]:
    """
    Generate CSV report for spreadsheet review.

    Columns:
    - Work#
    - Type
    - Pages
    - Title
    - Confidence
    - ImageCount
    - Operator Notes (empty for annotation)

    Args:
        works: List of work dictionaries from segmentation manifest

    Returns:
        List of rows (list of strings)
    """
    rows = [['Work#', 'Type', 'Pages', 'Title', 'Confidence', 'ImageCount', 'Operator Notes']]

    for work in works:
        work_number = work['work_number']
        work_type = work['type']
        pages_str = ','.join(str(p) for p in work.get('pages', []))
        title = work.get('title', '')[:100]
        confidence = f"{work['confidence']:.2f}"
        image_count = str(work.get('image_count', 0))
        notes = ''  # Operator can fill in

        rows.append([
            str(work_number),
            work_type,
            pages_str,
            title,
            confidence,
            image_count,
            notes
        ])

    return rows


# =============================================================================
# Report Writing
# =============================================================================

def write_html_report(html_content: str, output_path: Path) -> bool:
    """Write HTML report to file."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Generated HTML report: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to write HTML report: {e}")
        return False


def write_csv_report(rows: List[List[str]], output_path: Path) -> bool:
    """Write CSV report to file."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        logger.info(f"Generated CSV report: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to write CSV report: {e}")
        return False


# =============================================================================
# Main Entry Point
# =============================================================================

def generate_reports(
    container_id: int,
    manifest_path: Optional[Path] = None,
    segmentation_path: Optional[Path] = None,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generate QC reports for a container.

    Args:
        container_id: Container ID
        manifest_path: Path to page pack manifest (auto-detected if None)
        segmentation_path: Path to segmentation manifest (auto-detected if None)
        output_dir: Output directory (defaults to 0220_Page_Packs/{id}/qa/)

    Returns:
        Result dictionary with status and file paths
    """
    result = {
        'status': 'pending',
        'container_id': container_id,
        'html_report': None,
        'csv_report': None,
        'error_message': None,
    }

    # Auto-detect manifest paths if not provided
    if not manifest_path:
        manifest_path = Path('0220_Page_Packs') / str(container_id) / 'manifest.json'

    if not segmentation_path:
        segmentation_path = (Path('0220_Page_Packs') / str(container_id) /
                           'segmentation' / 'segmentation_v2_1.json')

    if not output_dir:
        output_dir = Path('0220_Page_Packs') / str(container_id) / 'qa'

    logger.info(f"Generating QC reports for Container {container_id}")
    logger.debug(f"Manifest: {manifest_path}")
    logger.debug(f"Segmentation: {segmentation_path}")
    logger.debug(f"Output: {output_dir}")

    try:
        # Load manifest
        if not manifest_path.exists():
            result['status'] = 'error'
            result['error_message'] = f"Manifest not found: {manifest_path}"
            logger.error(result['error_message'])
            return result

        with open(manifest_path) as f:
            manifest_data = json.load(f)

        # Load segmentation (optional)
        segmentation_data = None
        if segmentation_path.exists():
            with open(segmentation_path) as f:
                segmentation_data = json.load(f)
            logger.info(f"Loaded segmentation with {len(segmentation_data.get('works', []))} works")
        else:
            logger.warning(f"Segmentation not found: {segmentation_path}")

        # Generate HTML report
        html_content = generate_html_report(
            container_id,
            manifest_data,
            segmentation_data
        )

        html_path = output_dir / 'qc_report.html'
        if write_html_report(html_content, html_path):
            result['html_report'] = str(html_path)
        else:
            result['status'] = 'error'
            result['error_message'] = 'Failed to write HTML report'
            return result

        # Generate CSV report
        if segmentation_data:
            works = segmentation_data.get('works', [])
            csv_rows = generate_csv_report(works)

            csv_path = output_dir / 'qc_report.csv'
            if write_csv_report(csv_rows, csv_path):
                result['csv_report'] = str(csv_path)
            else:
                logger.warning('Failed to write CSV report')
        else:
            logger.info('Skipping CSV report (no segmentation data)')

        result['status'] = 'success'
        logger.info(f"QC reports generated successfully")
        return result

    except Exception as e:
        logger.exception(f"Report generation failed: {e}")
        result['status'] = 'error'
        result['error_message'] = str(e)
        return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate QC reports for operator review'
    )
    parser.add_argument(
        '--container-id',
        type=int,
        required=True,
        help='Container ID'
    )
    parser.add_argument(
        '--manifest-path',
        type=Path,
        help='Path to page pack manifest'
    )
    parser.add_argument(
        '--segmentation-path',
        type=Path,
        help='Path to segmentation manifest'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory for reports'
    )

    args = parser.parse_args()

    result = generate_reports(
        args.container_id,
        args.manifest_path,
        args.segmentation_path,
        args.output_dir
    )

    if result['status'] == 'success':
        logger.info(f"\n[SUCCESS] Reports generated")
        if result['html_report']:
            logger.info(f"  HTML: {result['html_report']}")
        if result['csv_report']:
            logger.info(f"  CSV: {result['csv_report']}")
        return 0
    else:
        logger.error(f"\n[FAILED] {result['error_message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
