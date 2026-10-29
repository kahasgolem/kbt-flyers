# Start here

This is a working offline Python parser, schedule-rule and export contract prototype. The editable visual template/editor is not implemented.

Read PUBLICATION_STATUS.md and SETUP.md. Python 3.12+ uses only the standard library:

```sh
python -B -m unittest discover -s tests -v
```

Source modules are in src/ and the extraction schema is in schema/. The tests use synthetic evidence. Original flyers, OCR evidence and private source documents are excluded. Windows OCR helper source is retained but is not run by this setup. No model, LocalAI server or dependency install is required.

No project-wide license was present in the prepared source; this handoff does not invent one.
