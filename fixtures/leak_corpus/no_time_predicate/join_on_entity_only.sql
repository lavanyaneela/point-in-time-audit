-- The join most teams ship: entity id alone.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
GROUP BY p.entity_id
