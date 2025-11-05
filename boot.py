import usb_cdc
import usb_hid

# Keep REPL over serial and enable keyboard HID
usb_cdc.enable(console=True, data=True)
usb_hid.enable((usb_hid.Device.KEYBOARD,))
