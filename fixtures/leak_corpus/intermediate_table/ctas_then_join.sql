-- The naive join is upstream. The consumption site reads a clean looking table.
CREATE TABLE entity_latest AS
SELECT entity_id, MAX(value) AS latest_value, MAX(fact_time) AS latest_fact
FROM events
GROUP BY entity_id;

SELECT p.entity_id, l.latest_value
FROM predictions AS p
JOIN entity_latest AS l
  ON l.entity_id = p.entity_id
