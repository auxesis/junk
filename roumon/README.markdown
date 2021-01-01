# roumon

roumon shows what devices are connected to what access points.

Run it with:

```
go run main.go -username <username> -password <password> -address <address>
```

Polls the target device and outputs something like this:

```
|------------------------|-----------|-----------|
|      DEVICE NAME       | RX SIGNAL | INTERFACE |
|------------------------|-----------|-----------|
| 94:58:CB:90:58:95      | -72       | lounge-2  |
| Downstairs             | -64       | lounge-1  |
| Joes-iPad              | -65       | office-2  |
| HP65A3BF               | -44       | office-1  |
|------------------------|-----------|-----------|
```
