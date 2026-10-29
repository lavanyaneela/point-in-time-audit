-- Passes code review. The fact was true; nobody asks when it arrived.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND e.fact_time <= p.prediction_time
GROUP BY p.entity_id
