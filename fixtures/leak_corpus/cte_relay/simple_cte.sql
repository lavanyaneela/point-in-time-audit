WITH latest AS (
    SELECT entity_id, MAX(value) AS latest_value
    FROM events
    GROUP BY entity_id
)
SELECT p.entity_id, latest.latest_value
FROM predictions AS p
JOIN latest
  ON latest.entity_id = p.entity_id
