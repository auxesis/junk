package main

import (
	"fmt"
	"os"
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/mattn/go-sqlite3"
	"tinygo.org/x/bluetooth"
)

type Device struct {
	Address string
	Name    string
	RSSI    int16
	Time    time.Time
}

var adapter = bluetooth.DefaultAdapter

// scan looks for Bluetooth devices, and emits them over a channel
func scan(ds chan Device) {
	// Enable BLE interface.
	must("enable BLE stack", adapter.Enable())

	// Start scanning.
	err := adapter.Scan(func(adapter *bluetooth.Adapter, device bluetooth.ScanResult) {
		ds <- Device{Address: device.Address.String(), Name: device.LocalName(), RSSI: device.RSSI, Time: time.Now()}
	})
	must("start scan", err)
}

func must(action string, err error) {
	if err != nil {
		panic("failed to " + action + ": " + err.Error())
	}
}

// prepareDB sets up a database for reading and writing
func prepareDB(path string) (db *sqlx.DB, err error) {
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

// logDevice stores devices seen
func logDevice(ds chan Device, db *sqlx.DB) {
	for d := range ds {
		_, err := db.NamedExec(`INSERT INTO devices (address,name,time,rssi) VALUES (:address,:name,:time,:rssi)`, d)
		if err != nil {
			fmt.Printf("error: %s\n", err)
		}
	}
}

// printStatus prints summary stats on devices seen
func printStatus(db *sqlx.DB) {
	var s struct {
		Count int
	}

	c := time.Tick(5 * time.Second)
	for range c {
		b := time.Now().Add(-5 * time.Second)
		a := time.Now()

		err := db.Get(&s, "SELECT count(*) AS count FROM devices WHERE time > ? AND time < ?", b.Format("2006-01-02 15:04:05"), a.Format("2006-01-02 15:04:05"))
		if err != nil {
			fmt.Printf("error: unable to execute status query: %s\n", err)
			continue
		}
		fmt.Printf("Devices observed: %d\n", s.Count)
	}
}

// truncateHistory deletes device records older than 2 weeks, and runs hourly
func truncateHistory(db *sqlx.DB) {
	truncate := `DELETE FROM devices WHERE time < ?`
	b := time.Now().Add(-15 * 24 * time.Hour)
	c := time.Tick(1 * time.Hour)
	for range c {
		result, err := db.Exec(truncate, b.Format("2006-01-02 15:04:05"))
		if err != nil {
			fmt.Printf("error: unable to truncate: %s\n", err)
			continue
		}
		c, err := result.RowsAffected()
		if err != nil {
			fmt.Printf("error: unable to read count of truncation: %s\n", err)
			continue
		}
		fmt.Printf("Truncated records: %d\n", c)
	}
}

func main() {
	path := "./devices.sqlite3"
	db, err := prepareDB(path)
	if err != nil {
		fmt.Print("error: unable to access db: %s", err)
		os.Exit(1)
	}

	devices := make(chan Device)
	go scan(devices)
	go printStatus(db)
	go truncateHistory(db)

	logDevice(devices, db)
}
