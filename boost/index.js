const pry = require('pryjs');
const PoweredUP = require('node-poweredup');
const poweredUP = new PoweredUP.PoweredUP();

function sleep(ms) {
  return new Promise(resolve => {
    setTimeout(resolve, ms);
  });
}

poweredUP.on('discover', async hub => {
  // Wait to discover a Hub
  console.log(`Discovered ${hub.name}!`);
  if (hub.type == 5) {
    return;
  }
  await hub.connect(); // Connect to the Hub
  const motorA = await hub.waitForDeviceAtPort('A'); // Make sure a motor is plugged into port A
  const motorB = await hub.waitForDeviceAtPort('B'); // Make sure a motor is plugged into port B
  const motorC = await hub.waitForDeviceAtPort('D'); // Make sure a motor is plugged into port C
  console.log(`Connected to ${hub.name}!`);

  const forward = async function(speed = 75) {
    console.log(`Running motor A + B at speed ${speed}`);
    motorA.setPower(speed);
    motorB.setPower(speed);
  };

  const stop = async function() {
    motorA.brake();
    motorB.brake();
  };

  const left = async function() {
    motorA.setPower(-75);
    motorB.setPower(75);
    await sleep(1000);
    motorA.brake();
    motorB.brake();
  };

  const debug = function(label, object) {
    for (let [key, value] of Object.entries(object)) {
      console.log(`${label}: ${key}: ${value}`);
    }
  };

  while (true) {
    eval(pry.it);
  }
});

poweredUP.scan(); // Start scanning for Hubs
console.log('Scanning for Hubs...');
