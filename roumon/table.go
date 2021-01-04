package main

import (
	"flag"
	"fmt"
	"log"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	ui "github.com/gizak/termui/v3"
	"github.com/gizak/termui/v3/widgets"
	"gopkg.in/routeros.v2"
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

// Draw renders the UI
func Draw(nodes chan Nodes) {
	if err := ui.Init(); err != nil {
		log.Fatalf("failed to initialize termui: %v", err)
	}
	defer ui.Close()

	p := widgets.NewParagraph()
	p.Text = "roumon"
	p.TextStyle.Fg = ui.ColorWhite
	p.SetRect(0, 0, 70, 3)

	table1 := widgets.NewTable()
	table1.TextStyle = ui.NewStyle(ui.ColorWhite)
	table1.RowStyles[0] = ui.NewStyle(ui.ColorBlack, ui.ColorWhite, ui.ModifierBold)
	table1.SetRect(0, 3, 70, 20)
	table1.BorderStyle = ui.NewStyle(ui.ColorYellow)
	table1.RowSeparator = false
	table1.ColumnWidths = []int{40, 10, 20}

	bc := widgets.NewBarChart()
	bc.Title = "Wifi Client Count"
	bc.SetRect(70, 0, 115, 10)
	bc.BarWidth = 10
	bc.LabelStyles = []ui.Style{ui.NewStyle(ui.ColorWhite)}
	bc.NumStyles = []ui.Style{ui.NewStyle(ui.ColorBlack)}

	draw := func(ns *Nodes) {
		p.Text = fmt.Sprintf("roumon (last update %s)\n", time.Now())
		table1.Rows = ns.renderTableRowData()
		labels, values := ns.renderBarChartData()
		bc.Labels = labels
		bc.Data = values
		ui.Render(p, table1, bc)
	}

	uiEvents := ui.PollEvents()
	for {
		select {
		case e := <-uiEvents:
			switch e.ID {
			case "q", "<C-c>":
				return
			}
		case ns := <-nodes:
			draw(&ns)
		}
	}
}

// Node represents a device on the network
type Node struct {
	MacAddress  string
	Hostname    string
	AccessPoint string
	RxSignal    float64
	LastUpdated time.Time
}

// Location return a human readable location of the access point
func (n *Node) Location() string {
	return strings.Split(n.AccessPoint, "-")[0]
}

// DisplayName returns a consist, unique name for a node
func (n *Node) DisplayName() string {
	h := n.Hostname
	if h == "" {
		h = n.MacAddress
	}
	return h
}

// PollNodeNames scrapes mac addresses from DHCP leases
func PollNodeNames(sc *SafeClient, names chan Node) {
	cmd := "/ip/dhcp-server/lease/print"
	props := "mac-address,host-name"
	for {
		reply, err := sc.Run(cmd, "=.proplist="+props)
		if err != nil {
			log.Fatal(err)
		}
		t := time.Now()
		for _, re := range reply.Re {
			names <- Node{
				MacAddress:  re.Map["mac-address"],
				Hostname:    re.Map["host-name"],
				LastUpdated: t,
			}
		}
		time.Sleep(5 * time.Second)
	}
}

// PollWifiRegistrations scrapes mac addresses from DHCP leases
func PollWifiRegistrations(sc *SafeClient, names chan Node) {
	cmd := "/caps-man/registration-table/print"
	props := "interface,mac-address,rx-signal"

	for {
		reply, err := sc.Run(cmd, "=.proplist="+props)
		if err != nil {
			log.Fatal(err)
		}
		t := time.Now()
		for _, re := range reply.Re {
			s, err := strconv.ParseFloat(re.Map["rx-signal"], 64)
			if err != nil {
				s = -500
			}

			names <- Node{
				MacAddress:  re.Map["mac-address"],
				AccessPoint: re.Map["interface"],
				RxSignal:    s,
				LastUpdated: t,
			}
		}
		time.Sleep(1 * time.Second)
	}
}

// Nodes is a container of Node
type Nodes struct {
	mutex   sync.RWMutex
	mapping sync.Map // key is mac address
}

// Update updates the Node mapping
func (n *Nodes) Update(k string, v Node) {
	n.mapping.Store(k, v)
}

// Get returns a Node from the mapping
func (n *Nodes) Get(k string) (Node, bool) {
	v, ok := n.mapping.Load(k)
	if ok {
		return v.(Node), ok
	}
	return Node{}, ok
}

func (n *Nodes) renderTableRowData() (rs [][]string) {
	n.mapping.Range(func(k, v interface{}) bool {
		no := v.(Node)
		if no.Location() == "" {
			return true
		}
		r := []string{no.DisplayName(), fmt.Sprintf("%.1f", no.RxSignal), no.Location()}
		rs = append(rs, r)
		return true
	})
	sort.Slice(rs, func(i, j int) bool { return rs[i][0] < rs[j][0] })
	header := [][]string{{"Device Name", "RX Signal", "Interface"}}
	rs = append(header, rs...)
	return rs
}

func (n *Nodes) renderBarChartData() (labels []string, values []float64) {
	c := make(map[string]float64)
	n.mapping.Range(func(k, v interface{}) bool {
		no := v.(Node)
		if no.Location() == "" {
			return true
		}
		if _, ok := c[no.Location()]; ok {
			c[no.Location()]++
		} else {
			c[no.Location()] = 1.0
		}
		return true
	})

	for l := range c {
		labels = append(labels, l)
	}
	sort.Strings(labels)
	for _, l := range labels {
		values = append(values, c[l])
	}
	return labels, values
}

// CompileMapping updates the map with updates from the scrapers
func CompileMapping(nodes chan Nodes, names, regos chan Node) {
	var ns Nodes
	for {
		select {
		case n := <-names:
			if v, ok := ns.Get(n.MacAddress); ok {
				v.Hostname = n.Hostname
				v.LastUpdated = n.LastUpdated
				ns.Update(n.MacAddress, v)
			} else {
				ns.Update(n.MacAddress, n)
			}
		case n := <-regos:
			if v, ok := ns.Get(n.MacAddress); ok {
				v.AccessPoint = n.AccessPoint
				v.RxSignal = n.RxSignal
				v.LastUpdated = n.LastUpdated
				ns.Update(n.MacAddress, v)
			} else {
				ns.Update(n.MacAddress, n)
			}
		}
		nodes <- ns
	}
}

var (
	address  = flag.String("address", "192.168.88.1:8728", "Address")
	username = flag.String("username", "admin", "Username")
	password = flag.String("password", "admin", "Password")
	interval = flag.Duration("interval", 1*time.Second, "Interval")
)

func main() {
	flag.Parse()

	c, err := routeros.Dial(*address, *username, *password)
	if err != nil {
		log.Fatal()
	}
	sc := SafeClient{client: c}

	names, regos := make(chan Node), make(chan Node)
	nodes := make(chan Nodes)
	go PollNodeNames(&sc, names)
	go PollWifiRegistrations(&sc, regos)
	go CompileMapping(nodes, names, regos)
	Draw(nodes)
}
