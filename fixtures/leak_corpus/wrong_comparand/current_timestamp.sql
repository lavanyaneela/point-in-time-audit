-- Arrival is checked, against the wrong instant. True in backfills, false in time.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND e.fact_time <= p.prediction_time
 AND e.arrival_time <= CURRENT_TIMESTAMP()
GROUP BY p.entity_id
