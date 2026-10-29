INSERT INTO feature_staging
SELECT entity_id, SUM(value) AS total_value
FROM events
GROUP BY entity_id;

SELECT p.entity_id, s.total_value
FROM predictions AS p
JOIN feature_staging AS s
  ON s.entity_id = p.entity_id
