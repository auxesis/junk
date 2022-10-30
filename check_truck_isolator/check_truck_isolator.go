package main

import (
	"fmt"
	"os"
	"time"

	"github.com/alecthomas/kong"
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

// GetDeviceByMAC fetches information about a device by its MAC address
func GetDeviceByMAC(db *sqlx.DB, mac string) (d Device, err error) {
	b := time.Now().Add(-3 * time.Hour)

	err = db.Get(&d, "SELECT * FROM devices WHERE address = ? AND time > ? ORDER BY time DESC LIMIT 1", mac, b.Format("2006-01-02 15:04:05"))
	if err != nil {
		return d, err
	}
	return d, err
}

var cli struct {
	MACAddress string `help:"MAC of device to check" arg`
	SqlitePath string `help:"Path to SQLite DB" default:"./devices.sqlite3"`
}

func main() {
	kong.Parse(&cli)
	db, err := prepareDB(cli.SqlitePath)
	if err != nil {
		fmt.Printf("error: unable to access db: %s\n", err)
		os.Exit(1)
	}
	d, err := GetDeviceByMAC(db, cli.MACAddress)
	if err != nil {
		fmt.Printf("error: unable to get device information: %s\n", err)
		os.Exit(1)
	}
	fmt.Printf("%+v\n", d)
}
