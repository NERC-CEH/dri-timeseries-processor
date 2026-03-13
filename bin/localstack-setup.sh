#!/bin/sh
echo "Initializing localstack services"

echo "########### Creating level-0 bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-level-0 --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Creating processed bucket ###########"
awslocal s3api create-bucket --bucket ukceh-fdri-staging-timeseries-processed --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

echo "########### Load parquet data into level-0 bucket #########"

awslocal s3 cp /var/lib/localstack/parquet-data/raw/ s3://ukceh-fdri-staging-timeseries-level-0/ --recursive

echo "########### Load parquet data into processed bucket #########"

awslocal s3 cp /var/lib/localstack/parquet-data/processed/ s3://ukceh-fdri-staging-timeseries-processed/ --recursive

echo "########### Load flux data into level-0 bucket ###########"

awslocal s3 cp /var/lib/localstack/flux-data/ s3://ukceh-fdri-staging-timeseries-level-0/ --recursive
