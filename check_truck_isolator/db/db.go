package db

import (
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/mattn/go-sqlite3"
)

type Device struct {
	ID      int
	Address string
	Name    string
	RSSI    int16
	Time    time.Time
}

// PrepareDB sets up a database for reading and writing
func PrepareDB(path string) (db *sqlx.DB, err error) {
	db, err = sqlx.Open("sqlite3", path)
	if err != nil {
		return db, err
	}

	schema := `
        CREATE TABLE IF NOT EXISTS devices (id INTEGER PRIMARY KEY AUTOINCREMENT, address STRING, name TEXT, time DATETIME, rssi INTEGER);
        `
	_, err = db.Exec(schema)
	return db, err
}
