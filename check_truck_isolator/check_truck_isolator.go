package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"github.com/alecthomas/kong"
	"io"
	"log"
	"net/http"
	"net/url"
)

// KismetClient is an abstract client for the Kismet API
type KismetClient struct {
	HTTPClient *http.Client
	BaseURL    *url.URL
	APIKey     string
}

// NewKismetClient sets up a new KismetClient
func NewKismetClient(b *url.URL, t string) (k KismetClient) {
	k.HTTPClient = &http.Client{}
	k.BaseURL = b
	k.APIKey = t
	return k
}

// KismetDevice represents a device detected by Kismet
type KismetDevice struct {
	Name     string `json:"kismet.device.base.name"`
	LastTime int    `json:"kismet.device.base.last_time"`
	MacAddr  string `json:"kismet.device.base.macaddr"`
}

// GetKismetDeviceByMAC fetches information from Kismet about a device by its MAC address
func (k KismetClient) GetKismetDeviceByMAC(mac string) (d []KismetDevice) {
	client := k.HTTPClient

	fieldsRequest := map[string][]string{
		"fields": []string{"kismet.device.base.macaddr", "kismet.device.base.name", "kismet.device.base.last_time"},
	}

	byt, err := json.Marshal(fieldsRequest)
	if err != nil {
		log.Fatalln("error: json marshal:", err)
	}

	buf := bytes.NewBufferString("json=")
	_, err = buf.Write(byt)
	if err != nil {
		log.Fatalln("error: write buffer:", err)
	}

	u := k.BaseURL.JoinPath("/devices/by-mac").JoinPath(mac).JoinPath("devices.json")

	req, err := http.NewRequest("POST", u.String(), buf)
	if err != nil {
		log.Fatalln("error: new request:", err)
	}
	c := http.Cookie{Name: "KISMET", Value: k.APIKey}
	req.AddCookie(&c)
	// if we don't set this, the requested fields get ignored
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := client.Do(req)
	if err != nil {
		log.Fatalln("error: client do:", err)
	}
	if resp.StatusCode >= 400 {
		log.Printf("error: bad HTTP response: %d\n", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Fatalln("error: read body:", err)
	}

	if resp.StatusCode >= 400 {
		log.Fatalf("error: response body: %s\n", body)
	}

	err = json.Unmarshal(body, &d)
	if err != nil {
		log.Printf("error: json unmarshal body: %s", body)
		log.Fatalln("error: json unmarshal:", err)
	}

	return d
}

var cli struct {
	KismetAPIBase *url.URL `help:"Base URL of Kismet API" default:"http://192.168.88.60:2501/"`
	KismetAPIKey  string   `help:"API key to authenticate with"`
	MACAddress    string   `help:"MAC of device to check" arg`
}

func main() {
	kong.Parse(&cli)
	k := NewKismetClient(cli.KismetAPIBase, cli.KismetAPIKey)

	d := k.GetKismetDeviceByMAC(cli.MACAddress)
	fmt.Printf("%+v\n", d)
}
