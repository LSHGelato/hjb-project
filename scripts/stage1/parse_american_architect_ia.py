#!/usr/bin/env python3
"""
Parser for American Architect (and similar) SIM identifiers.

Handles these patterns:
1. Standard issue: sim_american-architect-and-architecture_[yyyy-mm-dd]_[vol]_[issue_num]
2. Index (annual): sim_american-architect-and-architecture_[yyyy]_[vol]_index
3. Index (split half-year): sim_american-architect-and-architecture_[monthrange-year]_[vol]_index
4. Regular issue: sim_american-architect-and-architecture_[yyyy-mm-dd]_[vol]_[issue_num]

Returns parsed data suitable for inserting into:
- publication_titles_t (if new)
- issues_t (one per issue date)
- containers_t (one per IA identifier)

Some final-December issues contain volume-supplement materials (300+ extra pages).
These are flagged but NOT split (containers_t keeps it whole; pages_t will mark them appropriately).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@dataclass
class ParsedIAIdentifier:
    """Result of parsing an IA SIM identifier"""
    
    # Raw input
    raw_identifier: str
    
    # Extracted data
    publication: str  # e.g., "american-architect-and-architecture"
    publication_short: str  # e.g., "american_architect"
    
    # Issue/Index details
    is_index: bool  # True if this is an index
    issue_date: Optional[datetime]  # Date of issue (if issue, not index)
    year: int  # Year (for all types)
    volume_num: int  # Roman numeral converted to int
    volume_roman: str  # Original Roman numeral (if available)
    issue_num: Optional[int]  # Issue number within volume (if issue, not index)
    
    # Half-year variant (for split indexes)
    half_year_range: Optional[str]  # "january-june", "july-december", etc.
    
    # Warnings/flags
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    @property
    def volume_label(self) -> str:
        """Human-readable volume label"""
        return self.volume_roman or str(self.volume_num)
    
    @property
    def issue_label(self) -> str:
        """Human-readable issue label"""
        if self.is_index:
            if self.half_year_range:
                return f"Index {self.half_year_range.replace('-', ' ').title()} {self.year}"
            else:
                return f"Index {self.year}"
        else:
            return f"Issue {self.issue_num}"
    
    @property
    def canonical_issue_key(self) -> str:
        """Key for deduplication (same issue, different scans, should have same key)"""
        if self.is_index:
            # All indexes use simple format: INDEX_[year]_[padded volume]
            # Half-year range is stored separately but NOT in canonical key
            # (allows for future Option 2: using actual date boundaries from issues_t)
            return f"INDEX_{self.year}_{self.volume_num:03d}"
        else:
            # Same issue date + volume = same logical issue
            date_str = self.issue_date.strftime("%Y%m%d")
            return f"ISSUE_{date_str}_{self.volume_num:03d}_{self.issue_num:04d}"


def roman_to_int(roman: str) -> int:
    """Convert Roman numeral to integer"""
    val = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }
    total = 0
    prev = 0
    for char in reversed(roman.upper()):
        if char not in val:
            raise ValueError(f"Invalid Roman numeral: {roman}")
        c = val[char]
        if c < prev:
            total -= c
        else:
            total += c
        prev = c
    return total


def parse_american_architect_identifier(ia_identifier: str) -> Optional[ParsedIAIdentifier]:
    """
    Parse an American Architect (or similar SIM) IA identifier.
    
    Args:
        ia_identifier: Full IA identifier (e.g., sim_american-architect-and-architecture_2021-01-15_1_1)
    
    Returns:
        ParsedIAIdentifier or None if parse failed
    """
    
    identifier = ia_identifier.strip()
    
    # Pattern: sim_[pub]_[yyyy-mm-dd]_[vol]_[issue]
    # Or:      sim_[pub]_[yyyy]_[vol]_index
    # Or:      sim_[pub]_[monthrange-yyyy]_[vol]_index
    
    # Extract publication and split into parts
    if not identifier.startswith("sim_"):
        log.warning(f"Not a SIM identifier: {identifier}")
        return None
    
    # Remove 'sim_' prefix
    rest = identifier[4:]
    
    # Split by underscore - but publication name has underscores too
    # Heuristic: publication ends when we hit a date pattern
    
    # Try to match the entire pattern
    pattern_variants = [
        # Standard issue: sim_[pub]_YYYY-MM-DD_[vol]_[issue]
        r'^(?P<pub>.+?)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<vol>\d+)_(?P<issue>\d+)$',
        
        # Index (annual): sim_[pub]_YYYY_[vol]_index
        r'^(?P<pub>.+?)_(?P<year>\d{4})_(?P<vol>\d+)_index$',
        
        # Index (half-year): sim_[pub]_[monthrange]-YYYY_[vol]_index
        r'^(?P<pub>.+?)_(?P<monthrange>[a-z]+-[a-z]+-\d{4})_(?P<vol>\d+)_index$',
    ]
    
    matched = None
    match_type = None
    
    for i, pattern in enumerate(pattern_variants):
        m = re.match(pattern, identifier[4:])  # Skip 'sim_'
        if m:
            matched = m
            match_type = i
            break
    
    if not matched:
        log.warning(f"Could not parse identifier: {identifier}")
        return None
    
    groups = matched.groupdict()
    
    # Parse based on match type
    pub = groups['pub'].replace('-', '_')
    pub_short = pub
    
    warnings = []
    
    if match_type == 0:  # Standard issue
        date_str = groups['date']
        issue_date = datetime.strptime(date_str, "%Y-%m-%d")
        year = issue_date.year
        volume_num = int(groups['vol'])
        issue_num = int(groups['issue'])
        is_index = False
        half_year_range = None
        
    elif match_type == 1:  # Annual index
        year = int(groups['year'])
        volume_num = int(groups['vol'])
        issue_date = None
        issue_num = None
        is_index = True
        half_year_range = None
        
    elif match_type == 2:  # Half-year index
        # Parse "january-june-1927" -> extract year and month range
        monthrange_str = groups['monthrange']
        parts = monthrange_str.rsplit('-', 1)  # Split from right to get year
        month_part = parts[0]  # "january-june"
        year = int(parts[1])
        volume_num = int(groups['vol'])
        issue_date = None
        issue_num = None
        is_index = True
        half_year_range = month_part
    
    # Try to extract roman numeral from publication title (format the volume)
    # This is heuristic - we'd normally get it from IA metadata
    volume_roman = f"V{volume_num}"  # Placeholder (would need IA metadata for actual)
    
    result = ParsedIAIdentifier(
        raw_identifier=identifier,
        publication=groups['pub'],
        publication_short=pub_short,
        is_index=is_index,
        issue_date=issue_date,
        year=year,
        volume_num=volume_num,
        volume_roman=volume_roman,
        issue_num=issue_num,
        half_year_range=half_year_range,
        warnings=warnings,
    )
    
    return result


def parse_batch(ia_identifiers: list[str]) -> list[ParsedIAIdentifier]:
    """Parse a list of IA identifiers"""
    results = []
    for ia_id in ia_identifiers:
        parsed = parse_american_architect_identifier(ia_id)
        if parsed:
            results.append(parsed)
            print(f"✓ {ia_id}")
            print(f"  Issue: {parsed.issue_label}, Volume: {parsed.volume_label}")
        else:
            print(f"✗ {ia_id}")
    return results


if __name__ == "__main__":
    # Test cases
    test_identifiers = [
        # Standard issues
        "sim_american-architect-and-architecture_1890-01-01_27_1",
        "sim_american-architect-and-architecture_1890-06-15_27_6",
        "sim_american-architect-and-architecture_1900-12-31_50_12",
        
        # Annual indexes
        "sim_american-architect-and-architecture_1890_27_index",
        "sim_american-architect-and-architecture_1900_50_index",
        
        # Half-year indexes (later variant)
        "sim_american-architect-and-architecture_january-june-1927_131_index",
        "sim_american-architect-and-architecture_july-december-1929_136_index",
        
        # Invalid
        "not_a_sim_identifier",
    ]
    
    print("Testing American Architect parser:\n")
    results = parse_batch(test_identifiers)
    
    print("\n" + "="*80)
    print("PARSED RESULTS:")
    print("="*80 + "\n")
    
    for parsed in results:
        print(f"Identifier: {parsed.raw_identifier}")
        print(f"  Type: {'Index' if parsed.is_index else 'Issue'}")
        print(f"  Year: {parsed.year}")
        print(f"  Volume: {parsed.volume_label} (num: {parsed.volume_num})")
        if parsed.issue_date:
            print(f"  Date: {parsed.issue_date.strftime('%Y-%m-%d')}")
        if parsed.issue_num:
            print(f"  Issue Num: {parsed.issue_num}")
        if parsed.half_year_range:
            print(f"  Half-Year: {parsed.half_year_range}")
        print(f"  Canonical Key: {parsed.canonical_issue_key}")
        if parsed.warnings:
            print(f"  ⚠️  Warnings: {', '.join(parsed.warnings)}")
        print()
