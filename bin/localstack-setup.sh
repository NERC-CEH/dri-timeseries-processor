#!/bin/sh
echo "Initializing localstack services"

echo "########### Creating level-0 bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-level-0 --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Creating qc bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-qc --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Load parquet data into level-0 bucket #########"
awslocal s3api put-object --bucket ukceh-fdri-staging-timeseries-level-0 --key PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-17.parquet --body /var/lib/localstack/parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-17.parquet
awslocal s3api put-object --bucket ukceh-fdri-staging-timeseries-level-0 --key PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-18.parquet --body /var/lib/localstack/parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-18.parquet
awslocal s3api put-object --bucket ukceh-fdri-staging-timeseries-level-0 --key PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-19.parquet --body /var/lib/localstack/parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-19.parquet
awslocal s3api put-object --bucket ukceh-fdri-staging-timeseries-level-0 --key SOILMET_30MIN_2024_LOOPED/2024-01/2024-01-21.parquet --body /var/lib/localstack/parquet-data/SOILMET_30MIN_2024_LOOPED/2024-01/2024-01-21.parquet
awslocal s3api put-object --bucket ukceh-fdri-staging-timeseries-level-0 --key SOILMET_30MIN_2024_LOOPED/2024-01/2024-01-22.parquet --body /var/lib/localstack/parquet-data/SOILMET_30MIN_2024_LOOPED/2024-01/2024-01-22.parquet