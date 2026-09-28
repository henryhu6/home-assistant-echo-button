#import <Foundation/Foundation.h>
#import <IOBluetooth/IOBluetooth.h>
#include <signal.h>
#include <stdio.h>

static volatile sig_atomic_t interrupted = 0;

static void handle_interrupt(int signal_number) {
    (void)signal_number;
    interrupted = 1;
}

static void print_device(IOBluetoothDevice *device) {
    NSString *name = device.nameOrAddress ?: @"unknown";
    NSString *address = device.addressString ?: @"unknown";
    printf("%s  %s  paired=%s connected=%s\n", address.UTF8String,
           name.UTF8String, device.isPaired ? "yes" : "no",
           device.isConnected ? "yes" : "no");
    fflush(stdout);
}

@interface EchoButtonProbe : NSObject <IOBluetoothDeviceInquiryDelegate, IOBluetoothRFCOMMChannelDelegate>
@property(nonatomic, strong) IOBluetoothDeviceInquiry *inquiry;
@property(nonatomic, strong) IOBluetoothDevice *device;
@property(nonatomic, strong) IOBluetoothRFCOMMChannel *channel;
@property(nonatomic, copy) NSString *serviceChoice;
@property(nonatomic, assign) BOOL done;
@property(nonatomic, assign) BOOL connected;
@property(nonatomic, assign) int result;
- (void)scan;
- (void)listenToAddress:(NSString *)address service:(NSString *)serviceChoice;
@end

@implementation EchoButtonProbe

- (BOOL)runUntilDoneOrInterruptWithStartupTimeout:(NSTimeInterval)seconds {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:seconds];
    while (!self.done && !interrupted) {
        if (!self.connected && [deadline timeIntervalSinceNow] <= 0) break;
        [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                                 beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
    }
    return self.done || self.connected || interrupted;
}

- (void)scan {
    self.result = 1;
    self.inquiry = [IOBluetoothDeviceInquiry inquiryWithDelegate:self];
    self.inquiry.inquiryLength = 10;
    self.inquiry.updateNewDeviceNames = YES;
    IOReturn status = [self.inquiry start];
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "Bluetooth inquiry failed to start: 0x%08x\n", status);
        return;
    }
    puts("Scanning Classic Bluetooth devices. Hold one Echo Button until its light turns orange.");
    fflush(stdout);
    BOOL completed = [self runUntilDoneOrInterruptWithStartupTimeout:30];
    if (!completed) fprintf(stderr, "Bluetooth inquiry timed out after 30 seconds.\n");
    if (!self.done) {
        self.inquiry.delegate = nil;
        [self.inquiry stop];
        NSArray *devices = self.inquiry.foundDevices;
        printf("Found %lu device(s) before stopping:\n", (unsigned long)devices.count);
        for (IOBluetoothDevice *device in devices) print_device(device);
        self.result = devices.count > 0 ? 0 : 1;
    }
}

- (void)deviceInquiryComplete:(IOBluetoothDeviceInquiry *)sender
                       error:(IOReturn)error aborted:(BOOL)aborted {
    if (error != kIOReturnSuccess) {
        fprintf(stderr, "Bluetooth inquiry failed: 0x%08x\n", error);
    } else if (!aborted) {
        NSArray *devices = sender.foundDevices;
        printf("Found %lu device(s):\n", (unsigned long)devices.count);
        for (IOBluetoothDevice *device in devices) print_device(device);
        self.result = 0;
    }
    self.done = YES;
}

- (void)listenToAddress:(NSString *)address service:(NSString *)serviceChoice {
    self.result = 1;
    self.serviceChoice = serviceChoice;
    self.device = [IOBluetoothDevice deviceWithAddressString:address];
    if (!self.device) {
        fprintf(stderr, "Invalid Bluetooth address: %s\n", address.UTF8String);
        return;
    }
    print_device(self.device);
    IOReturn status = [self.device performSDPQuery:self];
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "SDP query failed to start: 0x%08x\n", status);
        return;
    }
    puts("Querying advertised services...");
    fflush(stdout);
    BOOL completed = [self runUntilDoneOrInterruptWithStartupTimeout:45];
    if (!completed) fprintf(stderr, "SDP/RFCOMM connection timed out after 45 seconds.\n");
    if (self.channel) [self.channel closeChannel];
}

- (void)sdpQueryComplete:(IOBluetoothDevice *)device status:(IOReturn)status {
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "SDP query failed: 0x%08x\n", status);
        self.done = YES;
        return;
    }

    NSMutableArray<IOBluetoothSDPServiceRecord *> *rfcommServices = [NSMutableArray array];
    IOBluetoothSDPServiceRecord *selectedService = nil;
    for (IOBluetoothSDPServiceRecord *record in device.services) {
        BluetoothRFCOMMChannelID channelID = 0;
        if ([record getRFCOMMChannelID:&channelID] != kIOReturnSuccess) continue;
        NSString *serviceName = [record getServiceName] ?: @"unnamed";
        printf("RFCOMM service: %s, channel=%u, SPP=%s\n", serviceName.UTF8String,
               channelID, [record matchesUUID16:0x1101] ? "yes" : "no");
        IOBluetoothSDPDataElement *classIDs = [record getAttributeDataElement:0x0001];
        if (classIDs) printf("  Service class IDs: %s\n", classIDs.description.UTF8String);
        [rfcommServices addObject:record];
        if ([self.serviceChoice isEqualToString:@"rfc"]) {
            if ([serviceName localizedCaseInsensitiveContainsString:@"RFC SERVER"]) selectedService = record;
        } else if ([record matchesUUID16:0x1101] ||
                   [serviceName localizedCaseInsensitiveContainsString:@"SPP"]) {
            selectedService = record;
        }
    }

    if (!selectedService && rfcommServices.count == 1) selectedService = rfcommServices.firstObject;
    if (!selectedService) {
        fprintf(stderr, "Requested RFCOMM service was not found.\n");
        self.done = YES;
        return;
    }

    BluetoothRFCOMMChannelID channelID = 0;
    [selectedService getRFCOMMChannelID:&channelID];
    IOBluetoothRFCOMMChannel *channel = nil;
    status = [device openRFCOMMChannelAsync:&channel withChannelID:channelID delegate:self];
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "RFCOMM open failed to start: 0x%08x\n", status);
        self.done = YES;
        return;
    }
    self.channel = channel;
    printf("Opening %s service on discovered RFCOMM channel %u...\n",
           self.serviceChoice.UTF8String, channelID);
    fflush(stdout);
}

- (void)rfcommChannelOpenComplete:(IOBluetoothRFCOMMChannel *)channel status:(IOReturn)status {
    (void)channel;
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "RFCOMM connection failed: 0x%08x\n", status);
        self.done = YES;
        return;
    }
    self.connected = YES;
    self.result = 0;
    puts("RFCOMM connected. Press the button; Ctrl-C stops capture.");
    fflush(stdout);
}

- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)channel
                    data:(void *)dataPointer length:(size_t)dataLength {
    (void)channel;
    const unsigned char *bytes = dataPointer;
    printf("RX %zu bytes: ", dataLength);
    for (size_t index = 0; index < dataLength; index++) printf("%02x", bytes[index]);
    putchar('\n');
    fflush(stdout);
}

- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)channel {
    (void)channel;
    puts("RFCOMM disconnected.");
    fflush(stdout);
    self.done = YES;
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        signal(SIGINT, handle_interrupt);
        IOBluetoothHostController *controller = [IOBluetoothHostController defaultController];
        if (!controller) {
            fprintf(stderr, "No macOS Bluetooth controller is available.\n");
            return 1;
        }
        if (argc == 2 && strcmp(argv[1], "status") == 0) {
            printf("Bluetooth power: %s\n", controller.powerState == kBluetoothHCIPowerStateON ? "on" : "off");
            puts("Paired devices:");
            for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) print_device(device);
            return 0;
        }
        if (controller.powerState != kBluetoothHCIPowerStateON) {
            fprintf(stderr, "Bluetooth is off. Turn it on in System Settings > Bluetooth.\n");
            return 1;
        }
        EchoButtonProbe *probe = [EchoButtonProbe new];
        if (argc == 2 && strcmp(argv[1], "scan") == 0) {
            [probe scan];
        } else if ((argc == 3 || argc == 4) && strcmp(argv[1], "listen") == 0) {
            NSString *service = argc == 4 ? [NSString stringWithUTF8String:argv[3]] : @"spp";
            if (![service isEqualToString:@"spp"] && ![service isEqualToString:@"rfc"]) {
                fprintf(stderr, "Service must be spp or rfc.\n");
                return 2;
            }
            [probe listenToAddress:[NSString stringWithUTF8String:argv[2]] service:service];
        } else {
            fprintf(stderr, "Usage: %s status | scan | listen BLUETOOTH_ADDRESS [spp|rfc]\n", argv[0]);
            return 2;
        }
        return probe.result;
    }
}
