#!/usr/bin/env python3
"""
HJB Stage 2 - OCR Parser Module

Purpose:
- Parse DjVu XML files for OCR text extraction
- Parse HOCR HTML files (fallback when DjVu unavailable)
- Parse scandata.xml for page structure metadata

OCR Priority:
1. DjVu XML (better accuracy)
2. HOCR HTML (fallback)

Output: Structured page data ready for database insertion
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET
from html.parser import HTMLParser


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PageOCRData:
    """OCR data for a single page"""
    page_index: int  # 0-based
    ocr_text: str
    ocr_confidence: Optional[float]  # 0.00-1.00
    ocr_word_count: int
    ocr_char_count: int
    ocr_source: str  # "ia_djvu" or "ia_hocr"


@dataclass
class PageMetadata:
    """Page structure metadata from scandata.xml"""
    page_index: int  # 0-based
    page_number_printed: Optional[str]  # "i", "ii", "1", "Cover", etc.
    page_label: Optional[str]
    page_type: str  # Maps to ENUM: content, cover, index, toc, advertisement, plate, blank, other


# ============================================================================
# OCR Parsing - DjVu XML
# ============================================================================

def parse_djvu_xml(file_path: Path) -> List[PageOCRData]:
    """
    Parse DjVu XML and extract OCR for all pages.

    DjVu XML structure (typical):
    <DjVuXML>
      <BODY>
        <OBJECT ...>
          <PARAGRAPH>
            <LINE>
              <WORD coords="..." confidence="...">text</WORD>
              ...
            </LINE>
          </PARAGRAPH>
        </OBJECT>
      </BODY>
    </DjVuXML>

    Returns: List of PageOCRData (0-based page indices)
    """
    if not file_path.exists():
        return []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        print(f"  [WARNING] Failed to parse DjVu XML: {e}", file=sys.stderr)
        return []

    pages_data: List[PageOCRData] = []
    page_index = 0

    # Look for OBJECT elements (typically one per page in IA DjVu)
    for obj in root.findall(".//OBJECT"):
        page_text_parts: List[str] = []
        page_confidences: List[float] = []
        word_count = 0

        # Extract text from all WORD elements
        for word_elem in obj.findall(".//WORD"):
            word_text = word_elem.text or ""
            if word_text.strip():
                page_text_parts.append(word_text)
                word_count += 1

                # Extract confidence score if available
                confidence_str = word_elem.get("confidence")
                if confidence_str:
                    try:
                        # Confidence can be 0-100 or 0-1, normalize to 0-1
                        conf = float(confidence_str)
                        if conf > 1:
                            conf = conf / 100
                        page_confidences.append(conf)
                    except ValueError:
                        pass

        # Combine page text
        ocr_text = " ".join(page_text_parts)
        ocr_char_count = len(ocr_text)

        # Calculate average confidence
        ocr_confidence = None
        if page_confidences:
            ocr_confidence = round(sum(page_confidences) / len(page_confidences), 2)

        pages_data.append(
            PageOCRData(
                page_index=page_index,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                ocr_word_count=word_count,
                ocr_char_count=ocr_char_count,
                ocr_source="ia_djvu",
            )
        )

        page_index += 1

    return pages_data


# ============================================================================
# OCR Parsing - HOCR HTML
# ============================================================================

class HOCRPageParser(HTMLParser):
    """Parse HOCR HTML to extract page OCR data"""

    def __init__(self):
        super().__init__()
        self.pages: dict[int, dict] = {}
        self.current_page: Optional[int] = None
        self.in_word = False
        self.current_word = ""
        self.current_confidence = None

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)

        if tag == "div" and "ocr_page" in attrs_dict.get("class", ""):
            # Extract page number from id (e.g., "page_1" -> 0-based index)
            page_id = attrs_dict.get("id", "page_1")
            # Parse "page_1" or "page1" format
            match = re.search(r"page[_]?(\d+)", page_id, re.IGNORECASE)
            if match:
                page_num = int(match.group(1))
                # Convert to 0-based
                self.current_page = page_num - 1
                self.pages[self.current_page] = {
                    "text_parts": [],
                    "confidences": [],
                    "word_count": 0,
                }

        elif tag == "span" and "ocrx_word" in attrs_dict.get("class", ""):
            self.in_word = True
            # Extract confidence from title attribute (e.g., "bbox 100 200 150 220; x_wconf 95")
            title = attrs_dict.get("title", "")
            match = re.search(r"x_wconf\s+(\d+)", title)
            if match:
                conf = int(match.group(1))
                # Normalize to 0-1
                self.current_confidence = conf / 100

    def handle_data(self, data: str) -> None:
        if self.in_word and self.current_page is not None:
            text = data.strip()
            if text:
                self.current_word = text

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.in_word and self.current_page is not None:
            if self.current_word:
                self.pages[self.current_page]["text_parts"].append(self.current_word)
                self.pages[self.current_page]["word_count"] += 1

                if self.current_confidence is not None:
                    self.pages[self.current_page]["confidences"].append(
                        self.current_confidence
                    )

            self.in_word = False
            self.current_word = ""
            self.current_confidence = None


def parse_hocr_html(file_path: Path) -> List[PageOCRData]:
    """
    Parse HOCR HTML and extract OCR for all pages.

    HOCR structure (typical):
    <div class='ocr_page' id='page_1'>
      <div class='ocr_carea'>
        <p class='ocr_par'>
          <span class='ocrx_word' title='bbox 100 200 150 220; x_wconf 95'>word</span>
        </p>
      </div>
    </div>

    Returns: List of PageOCRData (0-based page indices)
    """
    if not file_path.exists():
        return []

    try:
        with file_path.open("r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        print(f"  [WARNING] Failed to read HOCR HTML: {e}", file=sys.stderr)
        return []

    parser = HOCRPageParser()
    try:
        parser.feed(html_content)
    except Exception as e:
        print(f"  [WARNING] Failed to parse HOCR HTML: {e}", file=sys.stderr)
        return []

    pages_data: List[PageOCRData] = []

    # Convert parsed pages to PageOCRData
    for page_index in sorted(parser.pages.keys()):
        page_info = parser.pages[page_index]

        ocr_text = " ".join(page_info["text_parts"])
        ocr_char_count = len(ocr_text)

        # Calculate average confidence
        ocr_confidence = None
        if page_info["confidences"]:
            ocr_confidence = round(
                sum(page_info["confidences"]) / len(page_info["confidences"]), 2
            )

        pages_data.append(
            PageOCRData(
                page_index=page_index,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                ocr_word_count=page_info["word_count"],
                ocr_char_count=ocr_char_count,
                ocr_source="ia_hocr",
            )
        )

    return pages_data


# ============================================================================
# Scandata XML Parsing
# ============================================================================

# Mapping from scandata pageType to database ENUM values
_PAGE_TYPE_MAPPING = {
    "cover page": "cover",
    "cover": "cover",
    "title": "cover",
    "title page": "cover",
    "normal": "content",
    "page": "content",
    "text": "content",
    "blank": "blank",
    "empty": "blank",
    "contents": "toc",
    "table of contents": "toc",
    "index": "index",
    "advertisement": "advertisement",
    "ad": "advertisement",
    "plate": "plate",
    "frontispiece": "plate",
    "illustration": "plate",
    "back cover": "cover",
    "inside back cover": "cover",
}


def map_page_type(scandata_type: Optional[str]) -> str:
    """
    Map scandata pageType to pages_t ENUM.

    Maps scandata types (case-insensitive) to database ENUM values:
    - "Cover Page" → "cover"
    - "Normal" → "content"
    - "Blank" → "blank"
    - "Contents" → "toc"
    - "Index" → "index"
    - etc.

    Default: "content" for unknown types

    Args:
        scandata_type: Page type from scandata.xml

    Returns:
        Database ENUM value (content, cover, index, toc, advertisement, plate, blank, other)
    """
    if not scandata_type:
        return "content"

    normalized = scandata_type.strip().lower()
    return _PAGE_TYPE_MAPPING.get(normalized, "content")


def parse_scandata_xml(file_path: Path) -> List[PageMetadata]:
    """
    Parse scandata.xml for page structure metadata.

    Scandata structure:
    <book>
      <pageData>
        <page>
          <pageNumber>Cover</pageNumber>
          <pageType>Cover Page</pageType>
        </page>
      </pageData>
    </book>

    Returns: List of PageMetadata (0-based page indices)
    """
    if not file_path.exists():
        return []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        print(f"  [WARNING] Failed to parse scandata.xml: {e}", file=sys.stderr)
        return []

    pages_data: List[PageMetadata] = []
    page_index = 0

    # Look for page elements
    for page_elem in root.findall(".//page"):
        page_number_elem = page_elem.find("pageNumber")
        page_type_elem = page_elem.find("pageType")

        page_number_printed = None
        if page_number_elem is not None and page_number_elem.text:
            page_number_printed = page_number_elem.text.strip()

        page_type_str = None
        if page_type_elem is not None and page_type_elem.text:
            page_type_str = page_type_elem.text.strip()

        page_type = map_page_type(page_type_str)

        # Create default page label if not provided
        page_label = (
            page_number_printed
            if page_number_printed
            else f"page_{page_index}"
        )

        pages_data.append(
            PageMetadata(
                page_index=page_index,
                page_number_printed=page_number_printed,
                page_label=page_label,
                page_type=page_type,
            )
        )

        page_index += 1

    return pages_data
