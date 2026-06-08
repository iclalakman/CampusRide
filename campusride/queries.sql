SELECT * FROM "User";
SELECT * FROM admin;
SELECT * FROM adminpermission;
SELECT * FROM passenger;
SELECT * FROM driver;
SELECT * FROM car;
SELECT * FROM post;
SELECT * FROM offer;
SELECT * FROM ride;
SELECT * FROM report;


-- List all rides driven by Badenur Turgut.
SELECT
    r.ride_ID,
    r.start_destination,
    r.end_destination,
    r.cost,
    r.rating,
    c.plate_number,
    c.brand,
    c.model
FROM ride r
JOIN offer o ON r.offer_ID = o.offer_ID
JOIN "User" u ON o.driver_ID = u.user_ID
JOIN car c ON r.plate_number = c.plate_number
WHERE u.name = 'Badenur'
  AND u.surname = 'Turgut'
ORDER BY r.ride_ID;

-- List the average rating of each driver based on completed rides.
SELECT
    u.user_ID,
    u.name AS driver_name,
    u.surname AS driver_surname,
    ROUND(AVG(r.rating)::NUMERIC, 2) AS average_rating
FROM driver d
JOIN "User" u ON d.user_ID = u.user_ID
JOIN offer o ON d.user_ID = o.driver_ID
JOIN ride r ON o.offer_ID = r.offer_ID
WHERE r.rating IS NOT NULL
GROUP BY u.user_ID, u.name, u.surname
ORDER BY average_rating DESC;

-- List all rides created from offers made for posts created by İclal Akman.
SELECT
    r.ride_ID,
    r.start_destination,
    r.end_destination,
    r.cost,
    r.rating,
    driver_user.name || ' ' || driver_user.surname AS driver
FROM ride r
JOIN offer o ON r.offer_ID = o.offer_ID
JOIN post p ON o.post_ID = p.post_ID
JOIN "User" passenger ON p.passenger_ID = passenger.user_ID
JOIN "User" driver_user ON o.driver_ID = driver_user.user_ID
WHERE passenger.name = 'İclal'
  AND passenger.surname = 'Akman'
ORDER BY r.ride_ID;


-- List all posts with the number of offers they received.
SELECT
    p.post_ID AS Post_ID,
    p.location AS Post_Location,
    p.date_time AS Request_Date_Time,
    COUNT(o.offer_ID) AS Number_Of_Offers
FROM
    post p
JOIN
    offer o ON p.post_ID = o.post_ID
GROUP BY
    p.post_ID, p.location, p.date_time
ORDER BY
    Number_Of_Offers DESC;


-- List all rides whose cost is greater than 1000 TL.
SELECT
    ride_ID AS Ride_ID,
    start_destination AS Start_Destination,
    end_destination AS End_Destination,
    cost AS Cost,
    rating AS Rating
FROM
    ride
WHERE
    cost > 1000
ORDER BY
    cost DESC;

-- Update driver rates according to the average rating of their completed rides.
-- Only drivers whose rate value is different from the new average are updated.
UPDATE Driver d
SET rate = sub.avg_rating
FROM (
    SELECT 
        o.driver_ID,
        ROUND(AVG(r.rating)::NUMERIC, 2) AS avg_rating
    FROM Offer o
    JOIN Ride r ON r.offer_ID = o.offer_ID
    WHERE r.rating IS NOT NULL
    GROUP BY o.driver_ID
) AS sub
WHERE d.user_ID = sub.driver_ID
  AND d.rate IS DISTINCT FROM sub.avg_rating
RETURNING d.user_ID, d.rate;


-- Insert a new offer only if the driver has enough car seats
-- and has not already made an offer for the same post.
INSERT INTO Offer (offer_ID, post_ID, driver_ID)
SELECT 'O008', p.post_ID, 7
FROM Post p
JOIN Car c ON c.driver_ID = 7
WHERE p.post_ID = 'P005'
  AND p.passenger_number <= c.seat_number
  AND NOT EXISTS (
      SELECT 1
      FROM Offer o
      WHERE o.post_ID = p.post_ID
        AND o.driver_ID = 7
  );

-- Delete offers that were not accepted for a specific post.
DELETE FROM Offer o
WHERE o.post_ID = 'P001'
  AND NOT EXISTS (
      SELECT 1
      FROM Ride r
      WHERE r.offer_ID = o.offer_ID
  )
RETURNING offer_ID, post_ID, driver_ID;

-- Apply a 10% discount to expensive rides with low ratings.
UPDATE Ride
SET cost = ROUND((cost * 0.90)::NUMERIC, 2)
WHERE cost > 1000
  AND rating < 4
RETURNING ride_ID, start_destination, end_destination, cost, rating;

	