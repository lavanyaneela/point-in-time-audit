SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND e.fact_time <= p.prediction_time
 AND e.arrival_time <= TIMESTAMP '2025-06-01 00:00:00'
GROUP BY p.entity_id
