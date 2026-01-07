=====================
Architecture Overview
=====================

The time series processor follows a metadata-driven, dependency-aware architecture with the several main components,
explained below.

System Flow Chart
=================

.. mermaid::
    :align: center

    flowchart TD
        Start([Command Line Interface - CLI]) --> Parse[Parse Arguments]
        Parse --> LoadConfig[Load Environment Configuration]

        LoadConfig --> BuildDAG[Build Dependency Graph]
        BuildDAG --> MetaAPI[(Metadata Store API)]
        MetaAPI --> BuildDAG
        BuildDAG --> TopoSort[Topological Sort<br/>Determine execution order]

        TopoSort --> Pipeline[Processing Pipeline]
        Pipeline --> StartLayer{{For each layer in DAG}}
        StartLayer --> StartProc{{For each dataset in layer}}
        StartProc --> StartLayer

        StartProc --> CheckMethod{Check<br/>Method Type}
        CheckMethod --> StartProc

        CheckMethod -->|LOAD| LoadRaw[Read raw parquet from S3]
        LoadRaw --> S3Reader[(S3 Storage Reader)]
        S3Reader --> LoadRaw
        LoadRaw --> CreateTF[Create TimeFrame<br/>Add initial flags]
        CreateTF --> NextDataset

        CheckMethod -->|PROCESS| Process[Run standard processing steps]
        Process --> RunCorr[Run Corrections]
        RunCorr --> RunQC[Run Quality Control Checks]
        RunQC --> RunInfill[Run Infilling]
        RunInfill --> SaveProc[Write to S3]
        SaveProc --> S3Writer[(S3 Storage Writer)]
        SaveProc --> NextDataset

        CheckMethod -->|AGGREGATE| Resample[Temporal Resampling]
        Resample --> SaveAgg[Write to S3]
        SaveAgg --> S3Writer
        SaveAgg --> NextDataset

        CheckMethod -->|DERIVE| Compute[Compute derived variable<br/>e.g., Net Radiation]
        Compute --> SaveDeriv[Write to S3]
        SaveDeriv --> S3Writer
        SaveDeriv --> NextDataset

        NextDataset([Next dataset])
        NextDataset -->|All done| NextLayer
        NextLayer([Next layer])
        NextLayer -->|All done| ExportMetrics[Export Metrics to Prometheus]
        ExportMetrics --> PrometheusGW[(Prometheus<br/>Pushgateway)]
        ExportMetrics --> Done([Processing Complete])

        classDef setup fill:#A8D5E2,stroke:#7CA9B8,stroke-width:2px
        classDef orchestration fill:#D4B5E8,stroke:#A78BBD,stroke-width:2px
        classDef processing fill:#B8E6D5,stroke:#8BB8A8,stroke-width:2px
        classDef storage fill:#C9C9C9,stroke:#9A9A9A,stroke-width:2px
        classDef completion fill:#C8E6C9,stroke:#9AB89C,stroke-width:2px

        class Start,Parse,LoadConfig setup
        class BuildDAG,TopoSort, orchestration
        class Pipeline,CheckMethod,StartLayer,StartProc,LoadRaw,CreateTF,Process,RunCorr,RunQC,RunInfill,Resample,Compute,SaveProc,SaveAgg,SaveDeriv,NextDataset,NextLayer processing
        class MetaAPI,S3Reader,S3Writer,PrometheusGW storage
        class ExportMetrics,Done completion

Core Components
===============

1. Command line interface (CLI)
-------------------------------

Command line interface supporting two processing modes:

- **Explicit mode**: Fine-grained control over specific site/variable/periodicity combinations
- **Cross-product mode**: Bulk processing across dimensions

See `CLI usage document <user_guide/cli_usage.html>`_.

2. Environment configuration
----------------------------

The processor is designed to run in multiple execution environments (e.g. local, staging, production), each with 
different requirements for specifying credentials, storage paths, and access control. Environment configuration
provides a single abstraction layer that supplies these values to the rest of the system.

The runtime environment is determined from the ``environment`` environment variable. If omitted, the default is
``LOCAL``.

Local Development
~~~~~~~~~~~~~~~~~

- ``environment = LOCAL``
- Reads from ``__assets__/env.cfg``
- Uses LocalStack for S3 (``endpoint_url`` configured)
- Sample data pre-loaded for testing
- Prometheus metrics pushed locally

Staging/Production
~~~~~~~~~~~~~~~~~~

- ``environment = PRODUCTION, STAGING``
- Reads from environment variables
- Uses AWS S3 directly
- Full dataset access
- Prometheus metrics pushed to gateway

Configuration Keys
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 60 20

   - - Key
     - Purpose
     - Environments
   - - AWS_DEFAULT_REGION
     - AWS region for S3 access
     - All
   - - AWS_ACCESS_KEY_ID
     - AWS access key (local only uses dummy values)
     - All
   - - AWS_SECRET_ACCESS_KEY
     - AWS secret key (local only uses dummy values)
     - All
   - - level_0_bucket
     - S3 bucket containing raw (Level 0) data
     - All
   - - processed_bucket
     - S3 bucket for processed output data
     - All
   - - metadata_api_url
     - FDRI metadata API endpoint
     - All
   - - endpoint_url
     - S3 endpoint override (LocalStack)
     - Local only
   - - pushgateway_url
     - Prometheus Pushgateway for metrics
     - Staging/Production

Environment Specific Behavior
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Different behaviors based on environment:

.. list-table:: Environment-Specific Differences
   :header-rows: 1
   :widths: 20 30 25 25

   - - Aspect
     - Local
     - Staging
     - Production
   - - S3 Access
     - LocalStack (localhost:4566)
     - AWS S3
     - AWS S3
   - - Credentials
     - Dummy values (test/test)
     - IAM role or K8s secrets
     - IAM role or K8s secrets
   - - Data Volume
     - Small test dataset
     - Full staging data
     - Full production data
   - - Metrics
     - Local Pushgateway (optional)
     - Staging Pushgateway
     - Production Pushgateway
   - - DuckDB Config
     - Path-style URLs, no SSL
     - Standard AWS config
     - Standard AWS config

3. Metadata Store
-----------------

All processing decisions are driven by metadata fetched from the FDRI metadata API:

- Dataset definitions and relationships
- Processing method configurations (corrections, QC, infilling)
- Site metadata (coordinates, altitude, operating periods)
- Dependency chains between datasets

API Endpoints Used
~~~~~~~~~~~~~~~~~~

.. code-block:: text

    /id/dataset?_view=timeseries
        - Fetch dataset metadata with processing specifications

    /id/dataset/{dataset_id}/_all_dependencies
        - Fetch complete recursive dependency tree

    /id/data-processing-configuration
        - Fetch correction/QC/infilling configurations

    /id/site/{site_id}
        - Fetch site metadata (location, altitude, etc.)

    /id/network/{network_id}
        - Fetch network metadata (sites in network)

API vs Domain Models
~~~~~~~~~~~~~~~~~~~~
The metadata store returns graph-oriented JSON optimised for semantic relationships and flexible metadata discovery.
The metadata is retrieved from the API into "api models", then is transformed into "domain models" (that reflect
internal processing needs rather than API structure) before it is consumed by the pipeline.

API Models
^^^^^^^^^^
The API models are Pydantic models, designed to extract all the required fields out of the metadata response and
perform validation on types and formats.

Domain Models
^^^^^^^^^^^^^
The API models don't provide "nice" objects to work with in the downstream processes. Field names, datatypes,
and nested structures often need to be resolved and normalised.

Domain models provide a strongly typed internal representation of metadata. These models are designed around the
processor use case, not the API schema. All API models are transformed into a domain model using mapping functions.

4. Dependency Graph Builder
---------------------------

The result is a directed acyclic graph (DAG) describing the dependency
relationships between datasets, including raw inputs, intermediate products,
and derived outputs.

Constructs a complete directed acyclic graph (DAG) of dataset dependencies by:

1. Fetching root datasets matching user selection
2. Recursively resolving all dependencies via ``_all_dependencies`` endpoint
3. Attaching processing configurations (corrections, QC, infilling)
4. Handling configuration-based dependencies (e.g., QC checks requiring battery voltage data)

This process produces a complete graph of the state of dependencies, where each node represents a dataset, and
each edge represents a dependency.

The resolver guarantees that the graph is acyclic. If a cycle is detected (e.g., dataset A depends on dataset B which
depends on dataset A), the resolver will fail.

The graph is topologically sorted to ensure dependencies are processed before dependents.

Example visualised for RN:

.. mermaid::

    graph LR
      %% --- Derived Variable ---
      RN_PROC["RN_30MIN_PROCESSED"]

      LWIN_PROC["LWIN_30MIN_PROCESSED"]
      LWOUT_PROC["LWOUT_30MIN_PROCESSED"]
      SWIN_PROC["SWIN_30MIN_PROCESSED"]
      SWOUT_PROC["SWOUT_30MIN_PROCESSED"]

      LWIN_RAW["LWIN_30MIN_RAW"]
      LWOUT_RAW["LWOUT_30MIN_RAW"]
      SWIN_RAW["SWIN_30MIN_RAW"]
      SWOUT_RAW["SWOUT_30MIN_RAW"]

      BATTV_RAW["BATTV_30MIN_RAW"]
      SCANS_RAW["SCANS_30MIN_RAW"]
      TA_RAW["TA_30MIN_RAW"]
      TNR01C_RAW["TNR01C_30MIN_RAW"]
      LWIN_UNC_RAW["LWIN_UNC_30MIN_RAW"]
      LWOUT_UNC_RAW["LWOUT_UNC_30MIN_RAW"]

      RN_PROC --> LWIN_PROC
      RN_PROC --> LWOUT_PROC
      RN_PROC --> SWIN_PROC
      RN_PROC --> SWOUT_PROC

      LWIN_PROC --> LWIN_RAW
      LWOUT_PROC --> LWOUT_RAW
      SWIN_PROC --> SWIN_RAW
      SWOUT_PROC --> SWOUT_RAW

      LWIN_RAW --> BATTV_RAW
      LWIN_RAW --> LWIN_UNC_RAW
      LWIN_RAW --> SCANS_RAW
      LWIN_RAW --> TA_RAW
      LWIN_RAW --> TNR01C_RAW

      LWOUT_RAW --> BATTV_RAW
      LWOUT_RAW --> LWOUT_UNC_RAW
      LWOUT_RAW --> SCANS_RAW
      LWOUT_RAW --> TA_RAW
      LWOUT_RAW --> TNR01C_RAW

      SWIN_RAW --> BATTV_RAW
      SWIN_RAW --> SCANS_RAW

      SWOUT_RAW --> BATTV_RAW
      SWOUT_RAW --> SCANS_RAW

      %% === Styling ===
      classDef base fill:#dcfce7,stroke:#15803d,stroke-width:1px,color:#000,font-size:11px;
      classDef raw fill:#fef3c7,stroke:#92400e,stroke-width:1px,color:#000,font-size:11px;
      classDef processed fill:#dbeafe,stroke:#1e3a8a,stroke-width:1px,color:#000,font-size:11px;
      classDef derived fill:#c7d2fe,stroke:#3730a3,stroke-width:2px,color:#000,font-weight:bold,font-size:12px;

      class BATTV_RAW,SCANS_RAW,TA_RAW,TNR01C_RAW,LWIN_UNC_RAW,LWOUT_UNC_RAW base;
      class LWIN_RAW,LWOUT_RAW,SWIN_RAW,SWOUT_RAW raw;
      class LWIN_PROC,LWOUT_PROC,SWIN_PROC,SWOUT_PROC processed;
      class RN_PROC derived;

5. Processing Pipeline
----------------------

The processing pipeline is the core execution engine responsible for transforming raw data into processed data.

The pipeline takes in a dependency graph, representing the datasets to be produced, along with their dependent datasets.
Each dataset is provided as a ``TimeSeriesContainer``, which encapsulates:

- dataset loading metadata (e.g. source bucket, column names, etc.)
- its resolved processing metadata (corrections, QC, infilling)
- A ``TimeFrame`` object that holds the actual data for the dataset

The pipeline iterates over all the nodes (datasets) in topological order, ensuring each dataset is processed only
after all its upstream dependencies have been completed and are available in memory. Each node contains instructions
on how it should be processed. That could be one of 4 steps:

- **LOAD**: Load raw input data into a ``TimeFrame`` object
- **PROCESS**: Apply processing stages (corrections, QC, infilling - in that order)
- **AGGREGATE**: Temporal aggregation, e.g. 30 minute to Daily data
- **DERIVE**: Derive non-observed dataset from other datasets (e.g. calculating net radiation from the measured
  components of radiation)

This continues until the graph root nodes (i.e. the originally requested datasets) have been produced. Results of these
datasets are saved using the configured output locations.

6. I/O Backend
--------------

The I/O backend provides a unified interface for reading and writing datasets, isolating the pipeline from
storage formats, storage locations, credential handling, and access protocols. All interaction with object storage
passes through this layer.

Reader
~~~~~~
The reader component loads dataset data and metadata from storage into memory:

- locating the dataset based on network, site, periodicity and date
- resolving storage paths or prefixes
- reading parquet data for the requested time period

The reader is environment-aware. It gets bucket selection and credential access from the configuration layer.

Writer
~~~~~~

The writer component saves completed ``TimeFrame`` objects back to storage:

- selecting output bucket and prefix (according to environment)
- partitioning data by date, network, site and resolution
- merging new results with existing data when appropriate
- writing parquet files

7. Prometheus Metrics
---------------------

The processor exports metrics to a Pushgateway:

- **Pipeline timing**: Total runtime, per-operation timings
- **Success/failure counts**: Datasets processed successfully or failed  
- **Data availability**: Datasets with no data available

Locally accessible at ``http://localhost:9091``
