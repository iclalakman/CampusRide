INSERT INTO "User" (user_ID, email, user_name, phone_number, name, surname, gender)
VALUES
(1, 'e252654@metu.edu.tr', 'miray35', '05514404885', 'Miray', 'Murat', 'Female'),
(2, 'e252673@metu.edu.tr', 'badenur48', '05324567891', 'Badenur', 'Turgut', 'Female'),
(3, 'e258460@metu.edu.tr', 'iclal26', '05431234567', 'İclal', 'Akman', 'Female'),
(4, 'e252701@metu.edu.tr', 'efe01', '05551234567', 'Efe', 'Demir', 'Male'),
(5, 'e252702@metu.edu.tr', 'zeynep02', '05339876543', 'Zeynep', 'Kaya', 'Female'),
(6, 'e252704@metu.edu.tr', 'mert03', '05445556677', 'Mert', 'Yılmaz', 'Male'),
(7, 'e252706@metu.edu.tr', 'deniz04', '05321112233', 'Deniz', 'Şahin', 'Male'),
(8, 'e252707@metu.edu.tr', 'elif05', '05553334455', 'Elif', 'Arslan', 'Female')
ON CONFLICT (user_ID) DO UPDATE SET
    email = EXCLUDED.email,
    user_name = EXCLUDED.user_name,
    phone_number = EXCLUDED.phone_number,
    name = EXCLUDED.name,
    surname = EXCLUDED.surname,
    gender = EXCLUDED.gender;


INSERT INTO admin (user_ID)
VALUES
(1),
(2),
(3)
ON CONFLICT DO NOTHING;


INSERT INTO adminpermission (user_ID, permission)
VALUES
(1, 'update'),
(1, 'delete'),
(1, 'edit'),
(1, 'review'),
(2, 'update'),
(2, 'delete'),
(2, 'edit'),
(2, 'review'),
(3, 'update'),
(3, 'delete'),
(3, 'edit'),
(3, 'review')
ON CONFLICT DO NOTHING;


INSERT INTO passenger (user_ID)
VALUES
(1),
(3),
(4),
(5),
(8)
ON CONFLICT DO NOTHING;


INSERT INTO driver (user_ID, rate)
VALUES
(2, 0.00),
(4, 0.00),
(6, 0.00),
(7, 0.00)
ON CONFLICT DO NOTHING;


INSERT INTO car (plate_number, brand, model, seat_number, driver_ID)
VALUES
('33 ABC 123', 'Mercedes', 'C180 Kompressor', 5, 2),
('34 EFE 456', 'Renault', 'Clio', 4, 4),
('06 MRT 789', 'Fiat', 'Egea', 5, 6),
('35 DNZ 246', 'Toyota', 'Corolla', 5, 7)
ON CONFLICT DO NOTHING;


INSERT INTO post (post_ID, passenger_number, location, date_time, passenger_ID)
VALUES
('P001', 2, 'METU NCC Dormitory', '2026-05-12 14:30:00', 3),
('P002', 1, 'METU NCC Library', '2026-05-13 09:00:00', 1),
('P003', 3, 'Kalkanlı Gate', '2026-05-14 17:45:00', 5),
('P004', 1, 'Engineering Faculty', '2026-05-15 11:15:00', 4),
('P005', 2, 'Main Cafeteria', '2026-05-16 18:00:00', 8)
ON CONFLICT DO NOTHING;


INSERT INTO offer (offer_ID, post_ID, driver_ID)
VALUES
('O001', 'P001', 2),
('O002', 'P001', 4),
('O003', 'P002', 6),
('O004', 'P003', 7),
('O005', 'P004', 2),
('O006', 'P005', 4),
('O007', 'P003', 6)
ON CONFLICT DO NOTHING;


INSERT INTO ride (ride_ID, start_destination, end_destination, cost, rating, offer_ID, plate_number)
VALUES
('R001', 'METU NCC Dormitory', 'Nicosia City Center', 1200.00, 5, 'O001', '33 ABC 123'),
('R002', 'METU NCC Library', 'Lefkoşa Bus Terminal', 900.00, 4, 'O003', '06 MRT 789'),
('R003', 'Kalkanlı Gate', 'Girne City Center', 1500.00, 2, 'O004', '35 DNZ 246'),
('R004', 'Engineering Faculty', 'Güzelyurt Center', 750.00, 5, 'O005', '33 ABC 123'),
('R005', 'Main Cafeteria', 'Nicosia City Center', 1100.00, 4, 'O006', '34 EFE 456')
ON CONFLICT DO NOTHING;

INSERT INTO report (ride_ID, user_ID)
VALUES
('R003', 5),
('R002', 1)
ON CONFLICT DO NOTHING;

UPDATE driver d
SET rate = sub.avg_rating
FROM (
    SELECT o.driver_ID, ROUND(AVG(r.rating)::NUMERIC, 2) AS avg_rating
    FROM offer o
    JOIN ride r ON r.offer_ID = o.offer_ID
    WHERE r.rating IS NOT NULL
    GROUP BY o.driver_ID
) AS sub
WHERE d.user_ID = sub.driver_ID;


SELECT setval(pg_get_serial_sequence('"User"', 'user_id'), (SELECT MAX(user_ID) FROM "User"));