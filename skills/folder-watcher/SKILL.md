# Folder Watcher Skill

## Purpose
Detect supported input files, wait until they are stable, and create image_tasks.

## Supported Extensions
`.cr3`, `.cr2`, `.nef`, `.arw`, `.dng`, `.jpg`, `.jpeg`

## Ignore Silently
Hidden files, `.tmp`, `.part`, `.crdownload`, `.xmp`, `.DS_Store`, files starting with `._`.

## Rules
- Do not create duplicate tasks for the same source path.
- Check file size across intervals before queueing.
- Unsupported visible files may create `SKIPPED` with `UNSUPPORTED_FILE_TYPE`.
