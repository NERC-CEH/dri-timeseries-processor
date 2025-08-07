#!/bin/sh
echo "Initializing localstack services"

echo "########### Creating level-0 bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-level-0 --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Creating processed bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-processed --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Load parquet data into level-0 bucket #########"

BUCKET="ukceh-fdri-staging-timeseries-level-0"
LOCAL_DIR="/var/lib/localstack/parquet-data"

# Loop through all parquet files in the directory and its subdirectories
find "$LOCAL_DIR" -type f -name "*.parquet" | while read -r FILEPATH; do
    # Extract the relative path after the base directory
    RELATIVE_PATH="${FILEPATH#$LOCAL_DIR/}"

    # Construct the S3 key
    S3_KEY="$RELATIVE_PATH"

    # Upload the file to the S3 bucket
    awslocal s3api put-object --bucket "$BUCKET" --key "$S3_KEY" --body "$FILEPATH"
done
