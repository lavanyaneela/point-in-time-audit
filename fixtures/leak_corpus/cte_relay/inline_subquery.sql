SELECT p.entity_id, x.latest_value
FROM predictions AS p
JOIN (
    SELECT entity_id, MAX(value) AS latest_value
    FROM events
    GROUP BY entity_id
) AS x
  ON x.entity_id = p.entity_id
