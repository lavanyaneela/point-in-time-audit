SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE e.fact_time > p.prediction_time - INTERVAL 90 DAY
  AND e.fact_time <= p.prediction_time
  AND e.arrival_time <= p.prediction_time
GROUP BY p.entity_id
