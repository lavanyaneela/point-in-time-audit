SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND p.prediction_time >= e.fact_time
GROUP BY p.entity_id
