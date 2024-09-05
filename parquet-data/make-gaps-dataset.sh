set -u

pushd () {
    command pushd "$@" > /dev/null
}

popd () {
    command popd "$@" > /dev/null
}

rm_rand_percent_of_rows() {
    target=$1
    percent=$2

    if [ "$percent" -gt 100 ]; then echo "Percentage must be 100 or less"; exit 1; fi
    if [ "$percent" -lt 0 ]; then echo "Percentage must be 0 or more"; exit 1; fi

    echo "Target is: '${target}'"
    echo "Will remove: ${percent}% of rows"

    duckdb -c \
        "SELECT COUNT(*) AS \"size_before\" FROM READ_PARQUET('${target}');

        COPY (
            SELECT * FROM READ_PARQUET('${target}') TABLESAMPLE reservoir($((100-$percent))%)
        ) TO '${target}.new' (FORMAT PARQUET);
        
        SELECT COUNT(*) AS \"size_after\" FROM READ_PARQUET('${target}.new');"
    
    mv "${target}.new" "${target}"
}

clean_dir="./cosmos"
gap_dir="./cosmos-with-gaps"
precip="PRECIP_1MIN_2024_LOOPED"

# Clear directory if it currently exists

initialise_dir() {
    rm -rf $gap_dir
    echo "Purged directory"
    mkdir $gap_dir
    cp -r "${clean_dir}/${precip}" "${gap_dir}/"
    
    # Make day length gaps
    rm ${gap_dir}/${precip}/2024-01/2024-01-18.parquet \
        ${gap_dir}/${precip}/2024-02/2024-02-03.parquet
}

echo "Do you wish to purge the gapped data directory?"
select yn in "Yes" "No"; do
    case $yn in
        Yes ) initialise_dir; break;;
        No )  break;;
    esac
done

#Move into directory
pushd "${gap_dir}/${precip}"
# Make gap that crosses midnight
target="2024-01/2024-01-30.parquet"
duckdb -c \
    "COPY (
        SELECT *
        FROM READ_PARQUET('${target}')
        WHERE strftime('%H:%M', "time") < '23:00'
    ) TO '${target}.new' (FORMAT PARQUET);"

mv "${target}.new" $target

echo "Cleared 2024-01-30 from 23:00"

target="2024-01/2024-01-30.parquet"
duckdb -c \
    "COPY (
        SELECT *
        FROM READ_PARQUET('${target}')
        WHERE strftime('%H:%M', \"time\") >= '01:00'
    ) TO '${target}.new' (FORMAT PARQUET);"

mv "${target}.new" $target

echo "Cleared 2024-01-31 before 01:00"

for file in ./**/*.parquet; do
    rm_rand_percent_of_rows $file 10
done
