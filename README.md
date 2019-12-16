# Osprey

Osprey is a system that checks the images produced by vendors in mass digitization projects by the Digitization Program Office, OCIO, Smithsonian. The system checks that the files pass a number of tests and displays the results in a Shiny dashboard. This allows the vendor, the project manager, and the unit to monitor the progress and detect problems early.

## Components

The system has two components:

 * [osprey](osprey) - Python3 tool that runs a series of checks on folders. Results are written to a Postgres database.
 * [dashboard](dashboard) - R/Shiny dashboard that reads the Postgres database and displays the results.

