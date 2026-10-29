WITH raw AS (
    SELECT entity_id, value, fact_time
    FROM events
),
rolled AS (
    SELECT entity_id, SUM(value) AS total
    FROM raw
    GROUP BY entity_id
)
SELECT p.entity_id, rolled.total
FROM predictions AS p
JOIN rolled
  ON rolled.entity_id = p.entity_id
