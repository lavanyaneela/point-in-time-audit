SELECT p.entity_id, COUNT(i.severity) AS incidents
FROM predictions AS p
JOIN incidents AS i
  ON i.entity_id = p.entity_id
GROUP BY p.entity_id
