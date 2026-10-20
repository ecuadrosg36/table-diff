"""Staged multiset comparison. No raw full-table transfers."""

from collections import Counter, defaultdict
from dataclasses import asdict

from .adapters import Adapter, Policy, family, ident, literal, normalized, table_name


def compare(
    source: Adapter,
    target: Adapter,
    table: str,
    keys: list[str],
    date_col: str,
    policy: Policy = Policy(),
    sample_limit: int = 20,
) -> dict:
    if not 0 <= policy.float_digits <= 12:
        raise ValueError("float digits must be between 0 and 12")
    if sample_limit < 0:
        raise ValueError("sample limit must be nonnegative")
    schemas = [db.schema(table) for db in (source, target)]
    if set(schemas[0]) != set(schemas[1]):
        raise ValueError("Column sets differ")
    columns = sorted(schemas[0])
    if not keys or any(k not in columns for k in [*keys, date_col]):
        raise ValueError("Key/date columns must exist")
    for c in columns:
        if family(schemas[0][c]) != family(schemas[1][c]):
            raise ValueError(f"Incompatible column type: {c}")
    # Project user data into generated aliases, never its original names.
    # The normalized relation contains only these aliases and fixed metadata.
    value_aliases = [ident(f"_value_{i}") for i in range(len(columns))]
    values = ", ".join(value_aliases)
    bases = []
    for db, schema in zip((source, target), schemas):
        expressions = {c: normalized(c, schema[c], db.postgres, policy) for c in columns}
        day = normalized(date_col, schema[date_col], db.postgres, policy)
        # ISO timestamp prefix groups in normalized UTC; NULL has its own bucket.
        day = f"substr({day}, 1, 14)" if family(schema[date_col]) == "timestamp" else day
        row = " || ".join(expressions[c] for c in columns)
        key = " || ".join(expressions[c] for c in keys)
        projected_values = ", ".join(
            f"{expressions[c]} AS {alias}" for c, alias in zip(columns, value_aliases)
        )
        bases.append(
            f"SELECT {day} AS _day, {key} AS _key, md5({row}) AS _hash, "
            f"{projected_values} FROM {table_name(table)}"
        )

    def summaries(db, base, group, where="TRUE"):
        # Sum four 32-bit limbs; commutative and duplicate-sensitive, unlike XOR.
        limbs = ", ".join(
            f"sum(('x' || substr(_hash,{i},8))::bit(32)::bigint)"
            if db.postgres
            else f"sum(CAST('0x' || substr(_hash,{i},8) AS BIGINT))"
            for i in (1, 9, 17, 25)
        )
        return {
            r[0]: tuple(r[1:])
            for r in db.query(
                f"WITH n AS ({base}) SELECT {group}, count(*), {limbs} FROM n "
                f"WHERE {where} GROUP BY {group}"
            )
        }

    days = [summaries(db, base, "_day") for db, base in zip((source, target), bases)]
    bad_days = sorted(
        d for d in days[0].keys() | days[1].keys() if days[0].get(d) != days[1].get(d)
    )
    result = dict(
        policy=asdict(policy),
        source_rows=sum(v[0] for v in days[0].values()),
        target_rows=sum(v[0] for v in days[1].values()),
        mismatching_days=bad_days,
        differing_keys=0,
        missing_source_keys=0,
        missing_target_keys=0,
        duplicate_source_keys=0,
        duplicate_target_keys=0,
        samples=[],
        schema=schemas,
    )
    # Inventory duplicate key groups globally, including otherwise matching days.
    duplicate_keys = set()
    for side, db, base in zip(("source", "target"), (source, target), bases):
        duplicates = db.query(
            f"WITH n AS ({base}) SELECT _key FROM n GROUP BY _key HAVING count(*) > 1"
        )
        result[f"duplicate_{side}_keys"] = len(duplicates)
        duplicate_keys.update(r[0] for r in duplicates)
    # Union mismatching days before key comparison to avoid double counting day moves.
    where_days = "_day IN (" + ",".join(literal(d) for d in bad_days) + ")" if bad_days else "FALSE"
    key_summaries = [
        summaries(db, base, "_key", where_days) for db, base in zip((source, target), bases)
    ]
    candidates = key_summaries[0].keys() | key_summaries[1].keys()
    # A duplicate key can also occur on a matching day. Reconcile its complete
    # group, or a removed duplicate could be mislabeled as a missing key.
    duplicate_candidates = sorted(candidates & duplicate_keys)
    for offset in range(0, len(duplicate_candidates), 500):
        batch = duplicate_candidates[offset : offset + 500]
        where = "_key IN (" + ",".join(literal(k) for k in batch) + ")"
        for db, base, summary in zip((source, target), bases, key_summaries):
            summary.update(summaries(db, base, "_key", where))
    paired_differences = []
    for key in sorted(candidates):
        ks = [{key: side[key]} if key in side else {} for side in key_summaries]
        if ks[0] == ks[1]:
            continue
        where = f"_key = {literal(key)}"
        if ks[0] and ks[1]:
            paired_differences.append(key)
        result["differing_keys"] += 1
        result["missing_source_keys"] += int(not ks[0])
        result["missing_target_keys"] += int(not ks[1])
        if len(result["samples"]) >= sample_limit:
            continue
        # Only bounded differing-key samples leave the databases. Fetch distinct
        # normalized variants with multiplicities, capped to avoid giant duplicate groups.
        rows = [
            db.query(
                f"WITH n AS ({base}) SELECT {values}, count(*) FROM n "
                f"WHERE {where} GROUP BY {values} ORDER BY {values} LIMIT 21"
            )
            for db, base in zip((source, target), bases)
        ]
        changes = columns
        if len(rows[0]) == len(rows[1]) == 1:
            changes = [c for i, c in enumerate(columns) if rows[0][0][i] != rows[1][0][i]]
        result["samples"].append(
            dict(
                key=key,
                columns=changes,
                source=rows[0],
                target=rows[1],
                truncated=any(len(r) == 21 for r in rows),
            )
        )
    # Resolve every present-on-both-sides differing key exactly. Transfer only
    # normalized differing rows, grouped as variants; never transfer an unfiltered table.
    exact_source = exact_target = 0
    column_counts = Counter()
    for offset in range(0, len(paired_differences), 500):
        batch = paired_differences[offset : offset + 500]
        where = "_key IN (" + ",".join(literal(k) for k in batch) + ")"
        variants = []
        for db, base in zip((source, target), bases):
            groups = defaultdict(Counter)
            for row in db.query(
                f"WITH n AS ({base}) SELECT _key, {values}, count(*) FROM n "
                f"WHERE {where} GROUP BY _key, {values}"
            ):
                groups[row[0]][tuple(row[1:-1])] = row[-1]
            variants.append(groups)
        for key in batch:
            left, right = variants[0][key], variants[1][key]
            exact_source += sum((left - right).values())
            exact_target += sum((right - left).values())
            # For duplicate groups, compare per-column multisets without inventing
            # a pairing between rows that share a key.
            for i, column in enumerate(columns):
                marginals = []
                for side in (left, right):
                    marginal = Counter()
                    for row, count in side.items():
                        marginal[row[i]] += count
                    marginals.append(marginal)
                if marginals[0] != marginals[1]:
                    column_counts[column] += 1
    result["exact_unmatched_source_variants_rows"] = exact_source
    result["exact_unmatched_target_variants_rows"] = exact_target
    result["exact_column_multiset_differing_keys"] = dict(column_counts)
    result["different"] = bool(
        bad_days or result["duplicate_source_keys"] or result["duplicate_target_keys"]
    )
    return result
