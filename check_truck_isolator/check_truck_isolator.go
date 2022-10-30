package main

import (
	"fmt"
	"os"
	"time"

	"github.com/alecthomas/kong"
	"github.com/auxesis/junk/check_truck_isolator/db"
	"github.com/jmoiron/sqlx"
	_ "github.com/mattn/go-sqlite3"
)

// GetDeviceByMAC fetches information about a device by its MAC address
func GetDeviceByMAC(db *sqlx.DB, mac string) (d db.Device, err error) {
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
	d, err := db.PrepareDB(cli.SqlitePath)
	if err != nil {
		fmt.Printf("error: unable to access db: %s\n", err)
		os.Exit(1)
	}
	de, err := GetDeviceByMAC(d, cli.MACAddress)
	if err != nil {
		fmt.Printf("error: unable to get device information: %s\n", err)
		os.Exit(1)
	}
	fmt.Printf("%+v\n", de)
}
