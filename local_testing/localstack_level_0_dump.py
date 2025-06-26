"""Module to help test the time series processor locally.

Extracts messages from the S3 level0 bucket and puts them into the localstack level0 bucket.

Update the constants to customise where and how to search for messages.
"""

import boto3
import datetime
import io

# Edit these constants
S3_BUCKET = 'ukceh-fdri-staging-timeseries-level-0'
LOCALSTACK_BUCKET = 'ukceh-fdri-staging-timeseries-level-0'
DATASET = 'LIVE_SOILMET_30MIN'
# Set sites as None to copy all sites
SITES = ['ALIC1', 'BUNNY']
START_DATE = datetime.datetime(2025, 1, 1, 0, tzinfo=datetime.timezone.utc)
END_DATE = datetime.datetime(2025, 6, 30, 0, tzinfo=datetime.timezone.utc)

# Create the required prefixes
PREFIXES = [f"cosmos/dataset={DATASET}"]

if SITES:
    PREFIXES = [f"cosmos/dataset={DATASET}/site={SITE}" for SITE in SITES]

# setup localstack client
localstack_client = boto3.client("s3", endpoint_url="http://localhost:4566")

# setup aws client
s3_client = boto3.client("s3")

# Can only return 1000 objects at a time so need some pagination
paginator = s3_client.get_paginator('list_objects')

for PREFIX in PREFIXES:
    page_iterator = paginator.paginate(Bucket=S3_BUCKET, Prefix=PREFIX)

    # Setup a counter to see how many objects transferred.
    # Useful for checking number roughly as expected based on time period
    no_of_objects = 0

    print(f"Extracting objects from {PREFIX} between {START_DATE} and {END_DATE}")

    for page in page_iterator:
        for item in page['Contents']:

            if START_DATE <= item['LastModified'] <= END_DATE:
                
                data = s3_client.get_object(Bucket=S3_BUCKET, Key=item['Key'])
                contents = io.BytesIO(data["Body"].read())

                # send contents to localstack
                localstack_client.put_object(Bucket=LOCALSTACK_BUCKET, Key=item['Key'], Body=contents)

                no_of_objects += 1


    print(f"Total number of objects copied: {no_of_objects}")

