# Measured TLC demo

Actual local run: 73.49 seconds for main comparison. Full January 2024 file.

All five injected mutation classes verified with assertions; synthetic key and string probe explicitly added.

# Table comparison

- source_rows: 2964624
- target_rows: 2854110
- differing_keys: 110815
- missing_source_keys: 0
- missing_target_keys: 110515
- duplicate_source_keys: 0
- duplicate_target_keys: 1
- mismatching days: 3

Hash agreement is probabilistic; normalization can hide intentional differences.

```json
{
  "policy": {
    "float_digits": 6,
    "timezone": "UTC",
    "trim": false,
    "empty_is_null": false
  },
  "source_rows": 2964624,
  "target_rows": 2854110,
  "mismatching_days": [
    "V26:2023-12-31",
    "V26:2024-01-01",
    "V26:2024-01-27"
  ],
  "differing_keys": 110815,
  "missing_source_keys": 0,
  "missing_target_keys": 110515,
  "duplicate_source_keys": 0,
  "duplicate_target_keys": 1,
  "samples": [
    {
      "key": "V10:100.000000;",
      "columns": [
        "tpep_pickup_datetime"
      ],
      "source": [
        [
          "V8:0.000000;",
          "V10:232.000000;",
          "V10:249.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V9:-2.500000;",
          "V9:-1.000000;",
          "V10:-13.500000;",
          "V9:-1.000000;",
          "V9:-0.500000;",
          "V8:1.000000;",
          "V8:4.000000;",
          "V1:N;",
          "V0:;",
          "V8:0.000000;",
          "V8:0.000000;",
          "V10:-18.500000;",
          "V26:2024-01-01T00:30:39.000000;",
          "V26:2024-01-01T00:18:24.000000;",
          "V8:2.160000;",
          "V10:100.000000;",
          1
        ]
      ],
      "target": [
        [
          "V8:0.000000;",
          "V10:232.000000;",
          "V10:249.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V9:-2.500000;",
          "V9:-1.000000;",
          "V10:-13.500000;",
          "V9:-1.000000;",
          "V9:-0.500000;",
          "V8:1.000000;",
          "V8:4.000000;",
          "V1:N;",
          "V0:;",
          "V8:0.000000;",
          "V8:0.000000;",
          "V10:-18.500000;",
          "V26:2024-01-01T00:30:39.000000;",
          "V26:2024-01-01T01:18:24.000000;",
          "V8:2.160000;",
          "V10:100.000000;",
          1
        ]
      ],
      "truncated": false
    },
    {
      "key": "V10:101.000000;",
      "columns": [
        "tpep_pickup_datetime"
      ],
      "source": [
        [
          "V8:0.000000;",
          "V10:232.000000;",
          "V10:249.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V9:13.500000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:1.000000;",
          "V8:4.000000;",
          "V1:N;",
          "V0:;",
          "V8:0.000000;",
          "V8:0.000000;",
          "V9:18.500000;",
          "V26:2024-01-01T00:30:39.000000;",
          "V26:2024-01-01T00:18:24.000000;",
          "V8:2.160000;",
          "V10:101.000000;",
          1
        ]
      ],
      "target": [
        [
          "V8:0.000000;",
          "V10:232.000000;",
          "V10:249.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V9:13.500000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:1.000000;",
          "V8:4.000000;",
          "V1:N;",
          "V0:;",
          "V8:0.000000;",
          "V8:0.000000;",
          "V9:18.500000;",
          "V26:2024-01-01T00:30:39.000000;",
          "V26:2024-01-01T01:18:24.000000;",
          "V8:2.160000;",
          "V10:101.000000;",
          1
        ]
      ],
      "truncated": false
    },
    {
      "key": "V10:102.000000;",
      "columns": [
        "tpep_pickup_datetime"
      ],
      "source": [
        [
          "V8:0.000000;",
          "V10:229.000000;",
          "V10:148.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V9:15.600000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:1.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:5.150000;",
          "V8:0.000000;",
          "V9:25.750000;",
          "V26:2024-01-01T00:54:14.000000;",
          "V26:2024-01-01T00:39:59.000000;",
          "V8:2.880000;",
          "V10:102.000000;",
          1
        ]
      ],
      "target": [
        [
          "V8:0.000000;",
          "V10:229.000000;",
          "V10:148.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V9:15.600000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:1.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:5.150000;",
          "V8:0.000000;",
          "V9:25.750000;",
          "V26:2024-01-01T00:54:14.000000;",
          "V26:2024-01-01T01:39:59.000000;",
          "V8:2.880000;",
          "V10:102.000000;",
          1
        ]
      ],
      "truncated": false
    },
    {
      "key": "V10:103.000000;",
      "columns": [
        "tpep_pickup_datetime"
      ],
      "source": [
        [
          "V8:0.000000;",
          "V10:236.000000;",
          "V10:237.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V8:5.100000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:2.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:2.020000;",
          "V8:0.000000;",
          "V9:12.120000;",
          "V26:2024-01-01T00:36:57.000000;",
          "V26:2024-01-01T00:34:59.000000;",
          "V8:0.680000;",
          "V10:103.000000;",
          1
        ]
      ],
      "target": [
        [
          "V8:0.000000;",
          "V10:236.000000;",
          "V10:237.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V8:5.100000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:2.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:2.020000;",
          "V8:0.000000;",
          "V9:12.120000;",
          "V26:2024-01-01T00:36:57.000000;",
          "V26:2024-01-01T01:34:59.000000;",
          "V8:0.680000;",
          "V10:103.000000;",
          1
        ]
      ],
      "truncated": false
    },
    {
      "key": "V10:104.000000;",
      "columns": [
        "tpep_pickup_datetime"
      ],
      "source": [
        [
          "V8:0.000000;",
          "V10:166.000000;",
          "V10:238.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V8:7.900000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:2.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:2.580000;",
          "V8:0.000000;",
          "V9:15.480000;",
          "V26:2024-01-01T00:51:58.000000;",
          "V26:2024-01-01T00:47:21.000000;",
          "V8:1.130000;",
          "V10:104.000000;",
          1
        ]
      ],
      "target": [
        [
          "V8:0.000000;",
          "V10:166.000000;",
          "V10:238.000000;",
          "V8:1.000000;",
          "V8:2.000000;",
          "V8:2.500000;",
          "V8:1.000000;",
          "V8:7.900000;",
          "V8:1.000000;",
          "V8:0.500000;",
          "V8:2.000000;",
          "V8:1.000000;",
          "V1:N;",
          "V0:;",
          "V8:2.580000;",
          "V8:0.000000;",
          "V9:15.480000;",
          "V26:2024-01-01T00:51:58.000000;",
          "V26:2024-01-01T01:47:21.000000;",
          "V8:1.130000;",
          "V10:104.000000;",
          1
        ]
      ],
      "truncated": false
    }
  ],
  "schema": [
    {
      "trip_id": "BIGINT",
      "VendorID": "INTEGER",
      "tpep_pickup_datetime": "TIMESTAMP",
      "tpep_dropoff_datetime": "TIMESTAMP",
      "passenger_count": "BIGINT",
      "trip_distance": "DOUBLE",
      "RatecodeID": "BIGINT",
      "store_and_fwd_flag": "VARCHAR",
      "PULocationID": "INTEGER",
      "DOLocationID": "INTEGER",
      "payment_type": "BIGINT",
      "fare_amount": "DOUBLE",
      "extra": "DOUBLE",
      "mta_tax": "DOUBLE",
      "tip_amount": "DOUBLE",
      "tolls_amount": "DOUBLE",
      "improvement_surcharge": "DOUBLE",
      "total_amount": "DOUBLE",
      "congestion_surcharge": "DOUBLE",
      "Airport_fee": "DOUBLE",
      "synthetic_note": "VARCHAR"
    },
    {
      "trip_id": "bigint",
      "VendorID": "integer",
      "tpep_pickup_datetime": "timestamp without time zone",
      "tpep_dropoff_datetime": "timestamp without time zone",
      "passenger_count": "bigint",
      "trip_distance": "double precision",
      "RatecodeID": "bigint",
      "store_and_fwd_flag": "text",
      "PULocationID": "integer",
      "DOLocationID": "integer",
      "payment_type": "bigint",
      "fare_amount": "double precision",
      "extra": "double precision",
      "mta_tax": "double precision",
      "tip_amount": "double precision",
      "tolls_amount": "double precision",
      "improvement_surcharge": "double precision",
      "total_amount": "double precision",
      "congestion_surcharge": "double precision",
      "Airport_fee": "double precision",
      "synthetic_note": "text"
    }
  ],
  "exact_unmatched_source_variants_rows": 300,
  "exact_unmatched_target_variants_rows": 301,
  "exact_column_multiset_differing_keys": {
    "tpep_pickup_datetime": 100,
    "fare_amount": 101,
    "synthetic_note": 101,
    "Airport_fee": 1,
    "DOLocationID": 1,
    "PULocationID": 1,
    "RatecodeID": 1,
    "VendorID": 1,
    "congestion_surcharge": 1,
    "extra": 1,
    "improvement_surcharge": 1,
    "mta_tax": 1,
    "passenger_count": 1,
    "payment_type": 1,
    "store_and_fwd_flag": 1,
    "tip_amount": 1,
    "tolls_amount": 1,
    "total_amount": 1,
    "tpep_dropoff_datetime": 1,
    "trip_distance": 1,
    "trip_id": 1
  },
  "different": true
}
```
