import peachyprinter

def callback(data):
    print data

api = peachyprinter.PrinterAPI()
printers = api.get_available_printers()
api.load_printer(printers[0])
print_api = api.get_print_api(callback=callback)
test_print_api = api.get_test_print_api()
test_print_name = test_print_api.test_print_names()
test_print = test_print_api.get_test_print(test_print_name[0],10,10,0.1)
print_api.print_layers(test_print)
