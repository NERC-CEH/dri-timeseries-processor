=========
CLI Usage
=========

The Time Series Processor includes a command-line interface (CLI) used to launch processing runs locally or via
workflow automation.

This document describes the CLI arguments, usage patterns, and operational behaviour.


Running the Processor
=====================

The processor CLI is invoked using:

.. code-block:: console

    python -m new_processor ...

The CLI accepts arguments defining:

 - **what** datasets to process
 - **over what time period**
 - **for which network**

Processing Modes
----------------

The CLI supports two dataset selection modes:
1. **explicit**: Allowing users to request datasets explicitly or;
2. **cross-product**: Allowing user to build dataset combinations.

These modes are **mutually exclusive**.

Explicit Mode
~~~~~~~~~~~~~

Fine-grained control over specific site/variable/periodicity combinations.

**Use when you need**:

* Exact control over which datasets to process
* Different periodicities for different sites
* Specific variable combinations per site

**Syntax**:

.. code-block:: bash

   python -m new_processor explicit
     --network NETWORK
     [--lookback DURATION | --start-date YYYY-MM-DD]
     [--end-date YYYY-MM-DD]
     --selection SITE VARIABLE PERIODICITY
     [--selection SITE2 VARIABLE2 PERIODICITY2 ...]

**Example**:

.. code-block:: bash

   python -m new_processor explicit 
     --network cosmos 
     --lookback P2D 
     --selection cosmos-alic1 TA PT30M
     --selection cosmos-bunny PA PT30M
     --selection cosmos-bunny PRECIP P1D

This processes:

* cosmos-alic1 site: Temperature (TA) at 30-minute resolution
* cosmos-bunny site: Air pressure (PA) at 30-minute resolution
* cosmos-bunny site: Precipitation (PRECIP) at daily resolution

Cross-Product Mode
~~~~~~~~~~~~~~~~~~

Bulk processing across dimensions. Omitted dimensions process all available values.

**Use when you need**:

* Same variables across multiple sites
* All combinations of sites and variables
* Bulk reprocessing operations

**Syntax**:

.. code-block:: bash

   python -m new_processor cross-product 
     --network NETWORK 
     [--lookback DURATION | --start-date YYYY-MM-DD] 
     [--end-date YYYY-MM-DD] 
     [--sites SITE1 SITE2 ...] 
     [--variables VAR1 VAR2 ...] 
     [--periodicities PER1 PER2 ...]

**Example**:

.. code-block:: bash

   python -m new_processor cross-product 
     --network cosmos 
     --lookback P2D 
     --sites cosmos-alic1 cosmos-bunny
     --variables TA PA 
     --periodicities PT30M

This processes **all combinations**: cosmos-alic1+TA+PT30M, cosmos-alic1+PA+PT30M, cosmos-bunny +TA+PT30M,
cosmos-bunny +PA+PT30M

**Omitting dimensions**:

.. code-block:: bash

   # Process ALL sites, ALL variables, ALL periodicities
   python -m new_processor cross-product --network cosmos --lookback P7D

   # Process ALL sites for specific variables
   python -m new_processor cross-product 
     --network cosmos 
     --lookback P7D 
     --variables TA PA

Site Names
----------
Uses the site IDs as found in the FDRI metadata API.  These are typically in the form `<network>-<site-id>`, but
theoretically could be anything.

**Examples:**

- ``cosmos-alic1`` - Alice Holt in the COSMOS network
- ``cosmos-bunny`` - Bunny Park in the COSMOS network
- ``fdri-se-carwe-01`` - Carreg Wen in the FDRI network

Variable Names
--------------

Uses the variable IDs as found in the `sourceColumnName` field within the FDRI metadata API datasets end point.
These are specific for any given site (though typically all sites in a network will have the same colum names).

**Examples (for COSMOS network):**

- ``TA`` - Air temperature
- ``PA`` - Air pressure
- ``RH`` - Relative humidity
- ``WS`` - Wind speed
- ``WD`` - Wind direction
- ``PRECIP`` - Precipitation
- ``SWIN`` - Incoming shortwave radiation
- ``SWOUT`` - Outgoing shortwave radiation
- ``LWIN`` - Incoming longwave radiation
- ``LWOUT`` - Outgoing longwave radiation
- ``RN`` - Net radiation
- ``PE`` - Potential evapotranspiration

Periodicity Values
------------------

Common periodicities (ISO8601 duration format):

* ``PT30M`` - 30 minutes
* ``PT1H`` - 1 hour
* ``P1D`` - 1 day

Core Arguments
--------------

Both modes share these parameters:

Network Selection
~~~~~~~~~~~~~~~~~

**Required**. Specify which network to process:

.. code-block:: bash

   --network {cosmos|fdri}

Date Range Selection
~~~~~~~~~~~~~~~~~~~~

Choose one of two methods to specify the date range:

**Method 1: Lookback Duration** (default)

Process data going backward from the end date:

.. code-block:: bash

   --lookback DURATION

* Default: ``P2D`` (2 days)
* Format: ISO8601 duration
* Cannot contain time components (no hours/minutes)

Valid examples:

* ``P1D`` - 1 day
* ``P7D`` - 7 days (1 week)
* ``P1M`` - 1 month
* ``P1Y`` - 1 year

Invalid examples:

* ``PT6H`` - Invalid (contains time component)

**Method 2: Explicit Start Date**

Specify an exact start date (mutually exclusive with ``--lookback``):

.. code-block:: bash

   --start-date YYYY-MM-DD

End Date
~~~~~~~~

Optional. Defaults to today:

.. code-block:: bash

   --end-date YYYY-MM-DD

Error Handling
--------------

Invalid Arguments
~~~~~~~~~~~~~~~~~

The CLI validates all arguments before processing. Examples include:

.. code-block:: bash

   # Invalid: Missing required network
   python -m new_processor cross-product --lookback P2D

   # Invalid: Time component in lookback
   python -m new_processor cross-product --network cosmos --lookback PT6H

   # Invalid: Both lookback and start-date
   python -m new_processor cross-product 
     --network cosmos 
     --lookback P2D 
     --start-date 2024-01-01
