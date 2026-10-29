SELECT p.entity_id, SUM(e.value) AS total
FROM predictions AS p
LEFT JOIN events AS e
  ON e.entity_id = p.entity_id
GROUP BY p.entity_id
