# Claude Code: Fix extract_pages_v2.py - Relative Path Bug

## The Problem
Script uses relative paths like `0220_Page_Packs\1\images\page_0000.jpg`
Should use absolute paths to the NAS Working_Files directory.

All 14 pages fail with FileNotFoundError on image save.

## What to Fix

### 1. Get Base Path
Find where the output directory is set. Add this at the top of the container processing section:
```python
base_working = Path(config['working_files_root']) / "0220_Page_Packs" / str(container_id)
images_dir = base_working / "images"
ocr_dir = base_working / "ocr"

# Create directories
images_dir.mkdir(parents=True, exist_ok=True)
ocr_dir.mkdir(parents=True, exist_ok=True)
```

`config['working_files_root']` should point to:
`\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Working_Files`

### 2. Fix Image Extraction
Wherever you save JP2→JPEG, use the full path:
```python
image_path = images_dir / f'page_{page_index:04d}.jpg'
img.save(image_path)
```

NOT relative `0220_Page_Packs\1\images\page_0000.jpg`

### 3. Fix OCR File Copying
Same thing - use full path:
```python
ocr_output = ocr_dir / ocr_filename
shutil.copy(ocr_source, ocr_output)
```

### 4. Fix Manifest Path
```python
manifest_path = base_working / "manifest.json"
```

## Test After Fix
```bash
python scripts/stage2/extract_pages_v2.py --container-id 1 --dry-run
```

Should show:
```
Pages with images: 14  (currently 0)
Pages with OCR: 14
```

And verify files exist:
```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Working_Files\0220_Page_Packs\1\images\page_0000.jpg
```

## Important Notes
- Use `Path()` objects for all path operations (cleaner, cross-platform)
- Check how OCR section currently handles paths - it's working, so follow that pattern
- The bug is localized to path construction, rest of logic is fine
- This is 15-30 minutes of work

That's it. No long documentation, just fix the paths and test.
