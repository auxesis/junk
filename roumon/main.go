package main

import (
	"flag"
	"io"
	"log"
	"os"
	"os/exec"
	"sort"
	"sync"
	"time"

	"github.com/olekukonko/tablewriter"
	"gopkg.in/routeros.v2"
)

var (
	address  = flag.String("address", "192.168.88.1:8728", "Address")
	username = flag.String("username", "admin", "Username")
	password = flag.String("password", "admin", "Password")
	interval = flag.Duration("interval", 1*time.Second, "Interval")
)

// SafeClient is a concurrency-safe wrapper of the RouterOS client
type SafeClient struct {
	mutex  sync.Mutex
	client *routeros.Client
}

// Run executes commands concurrently safely
func (sc *SafeClient) Run(c, p string) (*routeros.Reply, error) {
	sc.mutex.Lock()
	r, err := sc.client.Run(c, p)
	sc.mutex.Unlock()
	return r, err
}

// GetAddresses scrapes mac addresses from DHCP leases
func GetAddresses(sc *SafeClient, macs *map[string]string) {
	cmd := "/ip/dhcp-server/lease/print"
	props := "mac-address,host-name"
	for {

		reply, err := sc.Run(cmd, "=.proplist="+props)
		if err != nil {
			log.Fatal(err)
		}

		for _, re := range reply.Re {
			mac := re.Map["mac-address"]
			name := re.Map["host-name"]
			(*macs)[mac] = name
			if (*macs)[mac] == "" {
				(*macs)[mac] = mac
			}
		}

		time.Sleep(5 * time.Second)
	}
}

// Clear clears the terminal
func Clear() {
	cmd := exec.Command("clear") //Linux example, its tested
	cmd.Stdout = os.Stdout
	cmd.Run()
}

// PollAndPrintRegistrations scrapes mac addresses from DHCP leases
func PollAndPrintRegistrations(sc *SafeClient, macs *map[string]string, interval time.Duration) {
	cmd := "/caps-man/registration-table/print"
	props := "interface,mac-address,rx-signal"

	for {
		reply, err := sc.Run(cmd, "=.proplist="+props)
		if err != nil {
			log.Fatal(err)
		}

		table := NewTable(os.Stdout)
		table.SetHeader([]string{"Device Name", "RX Signal", "Interface"})
		r := [][]string{}

		for _, re := range reply.Re {
			mac := re.Map["mac-address"]
			iface := re.Map["interface"]
			rxSig := re.Map["rx-signal"]

			r = append(r, []string{(*macs)[mac], rxSig, iface})
		}
		sort.Slice(r, func(i, j int) bool { return r[i][0] < r[j][0] })
		table.AppendBulk(r)
		Clear()
		table.Render()
		time.Sleep(interval)
	}
}

// NewTable returns a table with standard formatting
func NewTable(out io.Writer) (t *tablewriter.Table) {
	t = tablewriter.NewWriter(out)
	t.SetBorders(tablewriter.Border{Left: true, Top: true, Right: true, Bottom: true})
	t.SetCenterSeparator("|")
	t.SetAlignment(tablewriter.ALIGN_LEFT)
	return t
}

func main() {
	flag.Parse()

	c, err := routeros.Dial(*address, *username, *password)
	if err != nil {
		log.Fatal(err)
	}
	sc := SafeClient{client: c}

	macs := make(map[string]string)
	go GetAddresses(&sc, &macs)
	PollAndPrintRegistrations(&sc, &macs, *interval)
}
