const pry = require('pryjs');
const PoweredUP = require('node-poweredup');
const poweredUP = new PoweredUP.PoweredUP();

function sleep(ms) {
  return new Promise(resolve => {
    setTimeout(resolve, ms);
  });
}

function isInteractive() {
  return process.argv[2] == 'repl';
}

poweredUP.on('discover', async hub => {
  const debug = function(label, object) {
    for (let [key, value] of Object.entries(object)) {
      console.log(`${label}: ${key}: ${value}`);
    }
  };

  // Wait to discover a Hub
  console.log(`Discovered ${hub.name}!`);
  await hub.connect(); // Connect to the Hub
  console.log(`Connected to ${hub.name}!`);

  console.log(`Battery level ${hub.batteryLevel}`);

  console.log(`Connecting LED`);
  const led = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.HUB_LED);
  console.log(`Connecting motor`);
  const motor = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.DUPLO_TRAIN_BASE_MOTOR);
  console.log(`Connecting speaker`);
  const speaker = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.DUPLO_TRAIN_BASE_SPEAKER);
  console.log(`Connecting color sensor`);
  const colorSensor = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.DUPLO_TRAIN_BASE_COLOR_SENSOR);
  console.log(`Connecting speedometer`);
  const speedometer = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.DUPLO_TRAIN_BASE_SPEEDOMETER);
  console.log(`Connecting voltage sensor`);
  const voltageSensor = await hub.waitForDeviceByType(PoweredUP.Consts.DeviceType.VOLTAGE_SENSOR);
  var state = 'running';
  var setState = s => {
    console.log('state', {before: state, after: s});
    state = s;
  };

  hub.on('color', (port, event) => {
    var color = event.color;
    console.log('Color:', color, PoweredUP.Consts.Color[color]);
    if (color == PoweredUP.Consts.Color.RED) {
      console.log('Stopping motor');
      setState('stopped');
      motor.brake();
      speaker.playSound(3);
      setTimeout(setState, 2500, 'running');
      /*
      sleep(2500);
      state = 'running';
      */

      //await(hub.sleep(2500));
      //state = 'running';
    }
  });

  /*
  hub.on('reflect', (port, reflect) => {
    debug('Reflect', reflect);
  });

  /*
  hub.on('speed', (port, speed) => {
    debug('Speed', speed);
  });

  hub.on('rgb', (port, rgb) => {
    debug('RGB', rgb);
  });
  */

  if (isInteractive()) {
    console.log('Dropping to repl');
    while (true) {
      eval(pry.it);
    }
  }

  while (true) {
    setInterval(() => console.log('state', state), 1000);
    if (state == 'running') {
      motor.setPower(50);
      //speaker.playTone(9);
      //speaker.playSound(9);
      await hub.sleep(500);
    }
  }

  /*
  hub.on('voltage', (port, voltage) => {
    debug('Voltage', voltage);
  });
  */
});

poweredUP.scan(); // Start scanning for Hubs
console.log('Scanning for Hubs...');
