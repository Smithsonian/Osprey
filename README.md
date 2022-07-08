# Osprey

Osprey is a system that checks the images produced by vendors in mass
digitization projects by the Collections Digitization program of the
Digitization Program Office, OCIO, Smithsonian.

The system checks that the files pass a number of tests and displays
the results in a Shiny dashboard. This allows the vendor, the
project manager, and the unit to monitor the progress and detect
problems early.

## Components

The system has two main components:

 * [image_validation](image_validation) - Python3 tool that runs a series of checks on folders. Results are written to a Postgres database.
 * [dashboard](dashboard) - Dashboard and QC system that reads the Postgres database and displays the results, written in Python/Flask.

The database schema is in [database](database).

## Under construction

 * A separate validator for audio files is in progress under [wav_validation](wav_validation).

## License

Available under the Apache License 2.0. Consult the [LICENSE](LICENSE) file for details.
