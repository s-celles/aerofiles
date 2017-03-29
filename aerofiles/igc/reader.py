import datetime


class Reader:
    """
    A reader for the IGC flight log file format.

    see http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
    """

    def __init__(self):
        self.reader = None

    def read(self, fp):

        self.reader = LowLevelReader(fp)

        logger_id = None
        task = None
        fix_record_extensions = None
        k_record_extensions = None
        header = {}
        fix_records = []
        dgps_records = []
        event_records = []
        satellite_records = []
        security_records = []
        k_records = []
        comment_records = []

        for line, error in self.reader:

            if error:
                raise InvalidIGCFileError

            line_type = line['type']

            if line_type == 'A':
                logger_id = line['value']
            elif line_type == 'B':
                fix_record = LowLevelReader.process_B_record(line['value'], fix_record_extensions)
                fix_records.append(fix_record)
            elif line_type == 'C':
                task = line['value']  # todo
            elif line_type == 'D':
                dgps_records.append(line['value'])
            elif line_type == 'E':
                event_records.append(line['value'])  # todo
            elif line_type == 'F':
                satellite_records.append(line['value'])
            elif line_type == 'G':
                security_records.append(line['value'])
            elif line_type == 'H':
                header.update(line['value'])
            elif line_type == 'I':
                fix_record_extensions = line['value']
            elif line_type == 'J':
                k_record_extensions = line['value']
            elif line_type == 'K':
                k_record = LowLevelReader.process_K_record(line['value'], k_record_extensions)
                k_records.append(k_record)
            elif line_type == 'L':
                comment_records.append(line['value'])

        # delete source inside header dict from last H-record
        del header['source']

        return dict(logger_id=logger_id,                            # A record
                    fix_records=fix_records,                        # B records
                    task=task,                                      # C records
                    dgps_records=dgps_records,                      # D records
                    event_records=event_records,                    # E records
                    satellite_records=satellite_records,            # F records
                    security_records=security_records,              # G records
                    header=header,                                  # H records
                    k_records=k_records,                            # K records
                    comment_records=comment_records,                # L records
                    )


class LowLevelReader:
    """
    A low level reader for the IGC flight log file format.

    see http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
    """

    def __init__(self, fp):
        self.fp = fp
        self.line_number = 0

    def __iter__(self):
        return self.next()

    def next(self):
        for line in self.fp:
            self.line_number += 1

            try:
                result = self.parse_line(line)
                if result:
                    yield (result, None)

            except Exception as e:
                e.line_number = self.line_number
                yield (None, e)

    def parse_line(self, line):

        record_type = line[0]
        decoder = self.get_decoder_method(record_type)

        return decoder(line)

    def get_decoder_method(self, record_type):
        decoder = getattr(self, 'decode_{}_record'.format(record_type))
        if not decoder:
            raise ValueError('Unknown record type')

        return decoder

    @staticmethod
    def decode_A_record(line):
        id_addition = None if len(line) == 7 else line[7:].strip()
        return {
            'type': 'A',
            'value': {
                'manufacturer': line[0:3],
                'id': line[3:6],
                'id-addition': id_addition
            }
        }

    @staticmethod
    def decode_B_record(line):
        return {
            'type': 'B',
            'value': {
                'time': LowLevelReader.decode_time(line[1:7]),
                'lat': LowLevelReader.decode_latitude(line[7:15]),
                'lon': LowLevelReader.decode_longitude(line[15:24]),
                'validity': line[24],
                'pressure_alt': int(line[25:30]),
                'gps_alt': int(line[30:35]),
                'start_index_extensions': 35,
                'extensions_string': line[35::].strip()
            }
        }

    @staticmethod
    def process_B_record(decoded_b_record, fix_record_extensions):

        i = decoded_b_record['start_index_extensions']
        ext = decoded_b_record['extensions_string']

        b_record = decoded_b_record
        del b_record['start_index_extensions']
        del b_record['extensions_string']

        for extension in fix_record_extensions:
            start_byte, end_byte = extension['bytes']
            start_byte -= i
            end_byte -= i

            b_record.update(
                {extension['extension_type']: int(ext[start_byte:end_byte])}
            )

        return b_record

    @staticmethod
    def decode_C_record(line):
        # todo
        value = None
        return {'type': 'C', 'value': value}

    @staticmethod
    def decode_D_record(line):

        qualifier = line[1]
        if qualifier == '1':
            qualifier = 'GPS'
        elif qualifier == '2':
            qualifier = 'DGPS'
        else:
            raise ValueError('This qualifier is not possible')

        return {
            'type': 'D',
            'value': {
                'qualifier': qualifier,
                'station_id': line[2:6]
            }
        }

    @staticmethod
    def decode_E_record(line):
        # todo
        value = None
        return {'type': 'E', 'value': value}

    @staticmethod
    def decode_F_record(line):

        time_str = line[1:7]
        time = LowLevelReader.decode_time(time_str)

        # each satelite ID should have two digits
        if (len(line.strip()) - 7) % 2 != 0:
            raise ValueError('F record formatting is incorrect')

        satelites = []
        no_satelites = (len(line.strip()) - 7) / 2

        starting_byte = 7
        for satelite_index in range(no_satelites):
            satelites.append(line[starting_byte:starting_byte+2])
            starting_byte += 2

        return {
            'type': 'F',
            'value': {
                'time': time,
                'satelites': satelites
            }
        }

    @staticmethod
    def decode_G_record(line):
        return {
            'type': 'G',
            'value': line.strip()[1::]
        }

    @staticmethod
    def decode_H_record(line):

        source = line[1]

        # three letter code
        tlc = line[2:5]

        if tlc == 'DTE':
            value = LowLevelReader.decode_H_utc_date(line)
        elif tlc == 'FXA':
            value = LowLevelReader.decode_H_fix_accuracy(line)
        elif tlc == 'PLT':
            value = LowLevelReader.decode_H_pilot(line)
        elif tlc == 'CM2':
            value = LowLevelReader.decode_H_copilot(line)
        elif tlc == 'GTY':
            value = LowLevelReader.decode_H_glider_model(line)
        elif tlc == 'GID':
            value = LowLevelReader.decode_H_glider_registration(line)
        elif tlc == 'DTM':
            value = LowLevelReader.decode_H_gps_datum(line)
        elif tlc == 'RFW':
            value = LowLevelReader.decode_H_firmware_revision(line)
        elif tlc == 'RHW':
            value = LowLevelReader.decode_H_hardware_revision(line)
        elif tlc == 'FTY':
            value = LowLevelReader.decode_H_manufacturer_model(line)
        elif tlc == 'GPS':
            value = LowLevelReader.decode_H_gps_receiver(line)
        elif tlc == 'PRS':
            value = LowLevelReader.decode_H_pressure_sensor(line)
        elif tlc == 'CID':
            value = LowLevelReader.decode_H_competition_id(line)
        elif tlc == 'CCL':
            value = LowLevelReader.decode_H_competition_class(line)
        else:
            raise ValueError('Invalid h-record')

        value.update({'source': source})

        return {'type': 'H', 'value': value}

    @staticmethod
    def decode_H_utc_date(line):
        date_str = line[5:11]
        return {'utc_date': LowLevelReader.decode_date(date_str)}

    @staticmethod
    def decode_H_fix_accuracy(line):
        fix_accuracy = line[5:].strip()
        return {'fix_accuracy': None} if fix_accuracy == '' else {'fix_accuracy': int(fix_accuracy)}

    @staticmethod
    def decode_H_pilot(line):
        pilot = line[11:].strip()
        return {'pilot': None} if pilot == '' else {'pilot': pilot}

    @staticmethod
    def decode_H_copilot(line):
        second_pilot = line[11:].strip()
        return {'second_pilot': None} if second_pilot == '' else {'second_pilot': second_pilot}

    @staticmethod
    def decode_H_glider_model(line):
        glider_model = line[16:].strip()
        return {'glider_model': None} if glider_model == '' else {'glider_model': glider_model}

    @staticmethod
    def decode_H_glider_registration(line):
        glider_registration = line[14:].strip()
        if glider_registration == '':
            return {'glider_registration': None}
        else:
            return {'glider_registration': glider_registration}

    @staticmethod
    def decode_H_gps_datum(line):
        gps_datum = line[17:].strip()
        return {'gps_datum': None} if gps_datum == '' else {'gps_datum': gps_datum}

    @staticmethod
    def decode_H_firmware_revision(line):
        firmware_revision = line[21:].strip()
        return {'firmware_revision': None} if firmware_revision == '' else {'firmware_revision': firmware_revision}

    @staticmethod
    def decode_H_hardware_revision(line):
        hardware_revision = line[21:].strip()
        return {'hardware_revision': None} if hardware_revision == '' else {'hardware_revision': hardware_revision}

    @staticmethod
    def decode_H_manufacturer_model(line):
        manufacturer = None
        model = None
        manufacturer_model = line[12:].strip().split(',')
        if manufacturer_model[0] != '':
            manufacturer = manufacturer_model[0]
        if len(manufacturer_model) == 2 and manufacturer_model[1].lstrip() != '':
            model = manufacturer_model[1]
        return {'manufacturer': manufacturer,
                'model': model}

    @staticmethod
    def decode_H_gps_receiver(line):

        # can contain string in maxalt? (YX.igc)
        # HFGPS:uBLOX_TIM-LP,16,max9000m

        manufacturer = None
        model = None
        channels = None
        max_alt = None

        # some IGC files use colon, others don't
        if line[5] == ':':
            gps_sensor = line[6:].lstrip().split(',')
        else:
            gps_sensor = line[5:].split(',')

        manufacturer = None
        model = None
        channels = None
        max_alt = None
        for detail_index, detail in enumerate(gps_sensor):
            if detail_index == 0:
                manufacturer, model = detail.split(':')
            elif detail_index == 1:
                channels = detail.strip()
            elif detail_index == 2:
                max_alt = detail.strip()

        return {'manufacturer': manufacturer,
                'model': model,
                'channels': channels,
                'max_alt': max_alt}

    @staticmethod
    def decode_H_pressure_sensor(line):

        # check whether pressure has same colon problem as gps_sensor

        # can contain string inside max alt? (YX.igc)
        # HFPRSPRESSALTSENSOR:INTERSEMA,MS5534A,max8000m

        manufacturer = None
        model = None
        max_alt = None

        # some IGC files use colon, others don't
        if line[19] == ':':
            pressure_sensor = line[20:].strip().split(',')
        else:
            pressure_sensor = line[19:].split(',')

        if len(pressure_sensor) >= 1:
            manufacturer = pressure_sensor[0] if pressure_sensor[0] != '' else None
        if len(pressure_sensor) >= 2:
            model = pressure_sensor[1] if pressure_sensor[1] != '' else None
        if len(pressure_sensor) == 3:
            max_alt = pressure_sensor[2] if pressure_sensor[2] != '' else None

        return {'manufacturer': manufacturer,
                'model': model,
                'max_alt': max_alt}

    @staticmethod
    def decode_H_competition_id(line):
        competition_id = line[19:].strip()
        return {'competition_id': None} if competition_id == '' else {'competition_id': competition_id}

    @staticmethod
    def decode_H_competition_class(line):
        competition_class = line[22:].strip()
        return {'competition_class': None} if competition_class == '' else {'competition_class': competition_class}

    @staticmethod
    def decode_I_record(line):
        extensions = LowLevelReader.decode_extension_record(line)
        value = None if len(extensions) == 0 else extensions
        return {'type': 'I', 'value': value}

    @staticmethod
    def decode_J_record(line):
        extensions = LowLevelReader.decode_extension_record(line)
        value = None if len(extensions) == 0 else extensions
        return {'type': 'J', 'value': value}

    @staticmethod
    def decode_K_record(line):
        return {
            'type': 'K',
            'value': {
                'time': LowLevelReader.decode_time(line[1:7]),
                'value_string': line.strip()[7::],
                'start_index': 7
            }
        }

    @staticmethod
    def process_K_record(decoded_k_record, k_record_extensions):

        i = decoded_k_record['start_index']
        t = decoded_k_record['time']
        val = decoded_k_record['value_string']

        k_record = {'time': t}
        for extension in k_record_extensions:

            start_byte, end_byte = extension['bytes']
            start_byte -= i
            end_byte -= i

            k_record[extension['extension_type']] = val[start_byte:end_byte]

        return k_record

    @staticmethod
    def decode_L_record(line):
        return {
            'type': 'L',
            'value': {
                'source': line[1:4],
                'comment': line[4::].strip()
            }
        }

    @staticmethod
    def decode_date(date_str):

        if len(date_str) != 6:
            raise ValueError('Date string does not have correct length')

        dd = int(date_str[0:2])
        mm = int(date_str[2:4])
        yy = int(date_str[4:6])

        current_year_yyyy = datetime.date.today().year
        current_year_yy = current_year_yyyy % 100
        current_century = current_year_yyyy - current_year_yy
        yyyy = current_century + yy if yy < current_year_yy else current_century - 100 + yy

        return datetime.date(yyyy, mm, dd)

    @staticmethod
    def decode_time(time_str):

        if len(time_str) != 6:
            raise ValueError('Time string does not have correct size')

        h = int(time_str[0:2])
        m = int(time_str[2:4])
        s = int(time_str[4:6])

        return datetime.time(h, m, s)

    @staticmethod
    def decode_extension_record(line):

        no_extensions = int(line[1:3])

        if no_extensions * 7 + 3 != len(line.strip()):
            raise ValueError('I record contains incorrect number of digits')

        extensions = []
        for extension_index in range(no_extensions):
            extension_str = line[extension_index * 7 + 3:(extension_index + 1) * 7 + 3]
            start_byte = int(extension_str[0:2])
            end_byte = int(extension_str[2:4])
            tlc = extension_str[4:7]

            extensions.append({'bytes': (start_byte, end_byte), 'extension_type': tlc})

        return extensions

    @staticmethod
    def decode_latitude(lat_string):
        # todo
        return lat_string

    @staticmethod
    def decode_longitude(lon_string):
        # todo
        return lon_string


class InvalidIGCFileError(Exception):
    pass
