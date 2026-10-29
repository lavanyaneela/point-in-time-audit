CREATE TABLE hop_one AS
SELECT entity_id, value, fact_time
FROM events;

CREATE TABLE hop_two AS
SELECT entity_id, MAX(value) AS worst
FROM hop_one
GROUP BY entity_id;

SELECT p.entity_id, h.worst
FROM predictions AS p
JOIN hop_two AS h
  ON h.entity_id = p.entity_id
