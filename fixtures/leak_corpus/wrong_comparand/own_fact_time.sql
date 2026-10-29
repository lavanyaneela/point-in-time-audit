SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND e.fact_time <= p.prediction_time
 AND e.arrival_time <= e.fact_time + INTERVAL 1 DAY
GROUP BY p.entity_id
