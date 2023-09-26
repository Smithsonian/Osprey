# Osprey

Osprey is a system that checks the images produced by vendors in mass
digitization projects by the Collections Digitization program of the
Digitization Program Office, OCIO, Smithsonian.

The system checks that the files pass a number of tests and displays
the results in a web dashboard. This allows the vendor, the
project manager, and the unit to monitor the progress and detect
problems early.

## Components

The system has two main components:

 * [Osprey Worker](https://github.com/Smithsonian/Osprey_Worker/) - Python tool that runs a series of checks on folders. Results are sent to the dashboard via an HTTP API to be saved to the database.
 * [Osprey Misc](https://github.com/Smithsonian/Osprey_Misc/) - Database and scripts.

## License

Available under the Apache License 2.0. Consult the [LICENSE](LICENSE) file for details.
