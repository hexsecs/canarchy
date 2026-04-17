# Test Spec: `export` Command

## Coverage goals

* capture file export to `.json`
* capture file export to `.jsonl`
* saved session export to `.json`
* `.jsonl` rejection for sources without events
* unsupported source error
* unsupported destination format error

## Test cases

### Capture file to JSON

**Setup:** use a representative candump fixture.  
**Action:** run `canarchy export sample.candump artifact.json --json`.  
**Assert:** the destination file exists, contains a structured envelope, and includes serialized frame events.

### Capture file to JSONL

**Setup:** use a representative candump fixture.  
**Action:** run `canarchy export sample.candump artifact.jsonl --json`.  
**Assert:** the destination file contains one serialized event per line.

### Saved session to JSON

**Setup:** save a session first.  
**Action:** run `canarchy export session:lab-a artifact.json --json`.  
**Assert:** the destination file contains a structured envelope with a session payload.

### Session to JSONL rejected

**Setup:** save a session first.  
**Action:** run `canarchy export session:lab-a artifact.jsonl --json`.  
**Assert:** exit code 1 and `errors[0].code == "EXPORT_EVENTS_UNAVAILABLE"`.

### Unsupported source rejected

**Setup:** no matching capture file or session source.  
**Action:** run `canarchy export unknown-source artifact.json --json`.  
**Assert:** exit code 1 and `errors[0].code == "EXPORT_SOURCE_UNSUPPORTED"`.

### Unsupported destination suffix rejected

**Setup:** valid exportable source.  
**Action:** run `canarchy export sample.candump artifact.txt --json`.  
**Assert:** exit code 1 and `errors[0].code == "EXPORT_FORMAT_UNSUPPORTED"`.

## Fixtures

* existing candump fixture files
* temporary directories for exported artifacts
* temporary session store content under `.canarchy/`

## What is not tested

* export to unwritable filesystem locations, which is environment-dependent
* future non-file export sinks or archive formats, which are out of scope for the first implementation
