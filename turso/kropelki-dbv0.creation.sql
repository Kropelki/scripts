CREATE TABLE `weather` (
	`timestamp` bigint PRIMARY KEY NOT NULL,
	`temperature` real,
	`humidity` real,
	`pressure` real,
	`illumination` real,
	`dew_point` real,
	`solar_voltage` real,
	`battery_voltage` real
);

CREATE INDEX `idx_timestamp` ON `weather` (`timestamp`);
