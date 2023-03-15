# Osprey

Osprey is a system that checks the images produced by vendors in mass
digitization projects by the Collections Digitization program of the
Digitization Program Office, OCIO, Smithsonian.

The system checks that the files pass a number of tests and displays
the results in a Shiny dashboard. This allows the vendor, the
project manager, and the unit to monitor the progress and detect
problems early.

## Components

This README is for the image_validation component - Python3 tool that runs a series of checks on folders. Results are written to a Postgres database.

## Requirements

To install the Python requirement, use pip:

```python
pip install -r requirements.txt
```

This includes the modules:

 * xmltodict
 * exifread
 * bitmath
 * psycopg2-binary
 * pandas
 * Pillow

In addition, it requires these programs:

 * [JHOVE](https://jhove.openpreservation.org/)
 * [Imagemagick](https://imagemagick.org/)
 * [exiftool](https://exiftool.org/)

## License

Available under the Apache License 2.0. Consult the [LICENSE](LICENSE) file for details.
