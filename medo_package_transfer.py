import configparser, traceback, os, shutil, logging, smtplib
from logging.handlers import RotatingFileHandler
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

# TODO: вынести logging level в settings.ini; добавить handler с utf-8 и ротацией

logging.basicConfig(handlers=[RotatingFileHandler('./app.log', maxBytes=10000000, backupCount=2)],
                    level=logging.DEBUG,
                    # filename='app.log',
                    # filemode='a',
                    format='%(asctime)s: %(levelname)s - %(message)s',
                    datefmt=DATETIME_FORMAT)


def get_config():
    config = configparser.ConfigParser()
    config.read("settings.ini", "utf8")

    # обязательные параметры
    source_path = config.get("MAIN", "source_path")
    destination_path = config.get("MAIN", "destination_path")
    # при отсутствии обязательных параметров вызываем исключение
    if source_path == "":
        raise Exception('В settings.ini в секции MAIN отсутствует обязательный параметр source_path')
    if destination_path == "":
        raise Exception('В settings.ini в секции MAIN отсутствует обязательный параметр destination_path')

    # опциональные параметры
    # секция BACKUP
    backup_path = config.has_option("BACKUP", "backup_path") and config.get("BACKUP", "backup_path") or False

    # секция EMAIL
    smtp_server = config.has_option("EMAIL", "smtp_server") and config.get("EMAIL", "smtp_server") or False
    mail_to = config.has_option("EMAIL", "mail_to") and config.get("EMAIL", "mail_to") or False
    mail_from = config.has_option("EMAIL", "mail_from") and config.get("EMAIL", "mail_from") or False

    # должны быть заполнены все параметры EMAIL. иначе - None
    if (smtp_server and mail_to and mail_from) == False:
        mail = None
    else:
        mail = {}
        mail["server"] = smtp_server
        mail["to"] = mail_to
        mail["from"] = mail_from

    # секция LOGS
    log_enable = config.has_option("LOGS", "log_enable") and config.get("LOGS", "log_enable") or False

    config_dict = {}
    config_dict["source_path"] = source_path
    config_dict["destination_path"] = destination_path
    config_dict["backup_path"] = backup_path
    config_dict["mail"] = mail
    config_dict["log_enable"] = log_enable
    return config_dict

def send_email(FROM, TO, email_server, message, *args):
    logging.debug("отправляем почту")
    logging.debug(FROM)
    logging.debug(TO)
    logging.debug(email_server)
    msg = MIMEMultipart()
    msg['From'] = FROM
    msg['To'] = TO
    msg['Subject'] = "[ОШИБКА] Скрипт medo_package_mover"
    msg.attach(MIMEText(message, 'plain'))
    server = smtplib.SMTP(email_server)

    # TODO: проверить отправку с авторизацией
    # server.starttls()
    # password = args[0]
    # server.login(msg['From'], password)
    # send the message via the server.
    try:
        logging.debug("пробуем отправить почту")
        server.sendmail(msg['From'], msg['To'], msg.as_string())
    except:
        logging.debug("не удалось отправить почту =(")
        raise Exception("Не удалось отправить email")
    finally:
        server.quit()

def write_main_error_to_file(exception_message):
    with open('ERRORS.txt', 'a', encoding="utf8") as f:
        now = datetime.now().strftime(DATETIME_FORMAT)
        f.write("***" + now + "***\n" + exception_message + "\n")


def config_folders_check(source, destination, backup):
    if not os.path.exists(source) or not os.path.isdir(source):
        raise Exception ("не найдена директория source_path {}".format(source))

    if not os.path.exists(destination) or not os.path.isdir(destination):
        raise Exception ("не найдена директория destination_path {}".format(destination))

    if not backup is False:
        if not os.path.exists(backup) or not os.path.isdir(backup):
            raise Exception("не найдена директория backup_path {}".format(backup))

    if source == destination or source == backup or destination == backup:
       raise Exception("найдены повторяющиеся директории в конфигурационном файле")


def get_source_folders_list(source_path):
    subfolders = [f.path for f in os.scandir(source_path) if f.is_dir()]
    if len(subfolders)>0:
        return subfolders
    return None

def get_text_without_whitespaces(info_file):
    # попадались невалидные ini-файлы с пробелами в начале строк. удаляем их
    with open(info_file) as f:
        try:
            line_lst = [line.lstrip() for line in f.readlines()]
        except UnicodeDecodeError:
            with open(info_file, encoding="utf-8") as f:
                line_lst = [line.lstrip() for line in f.readlines()]
        lines = ''.join(line_lst)
    return lines


def prepare_ini_text(info_file):
    # предобработка информации из ini/ltr файлов из-за невалидности файлов
    text = get_text_without_whitespaces(info_file)
    
    return text


def is_identical(list_a, list_b):
    if len(list_a) != len(list_b):
        return False
    if set(list_a) == set(list_b):
        return True
    else:
        return False



def get_files_from_ini_file(info_file):
    ini = configparser.ConfigParser(allow_no_value=True)
    # try:
    #     ini.read(info_file)
    #
    # except UnicodeDecodeError:
    #     # пробуем utf8
    #     ini.read(info_file, encoding="utf-8")
    #     # raise Exception("неверная кодировка в ini-файле {}".format(info_file))
    # except Exception:
    #     raise Exception("некорректный ini/ltr файл")

    # FIX. невалидные ini файлы вызывают исключения в модуле ConfigParser. Откроем файл и подготовим текст к парсингу
    try:
        text = prepare_ini_text(info_file)
        ini.read_string(text)
    except Exception:
        raise Exception("некорректный ini/ltr файл")

    if not ini.has_section("ФАЙЛЫ"):
        return None

    pocket_files = [os.path.split(ini.get("ФАЙЛЫ", i))[1] for i in ini.options("ФАЙЛЫ")]

    # в секции [ТЕКСТ] может быть ФАЙЛ=
    if ini.has_section("ТЕКСТ"):
        for key, item in ini.items("ТЕКСТ"):
            if key.lower() == "файл":
                pocket_files.append(item)

    return pocket_files

def lists_matched(folder_files, ini_files, ini_file_name):
    expected_files = ini_files.copy()
    expected_files.append(ini_file_name)
    if is_identical(expected_files, folder_files) is False:
        return False
    return True


def is_pocket_valid(folder_path):
    files = os.listdir(folder_path)
    # ищем ini/ltr-файл с описанием файлов пакета
    information_files_list = [_ for _ in files if _.endswith(".ini") or _.endswith(".ltr")]
    if len(information_files_list) != 1:
        raise Exception("в пакете не найден ini-файл или их несколько {}".format(folder_path))

    # получаем список файлов пакета из ini/ltr
    expected_files = get_files_from_ini_file(os.path.join(folder_path, information_files_list[0]))
    if expected_files is None:
        raise Exception("не найден перечень файлов в ini-файле пакета {}".format(folder_path))

    # проверяем целостность пакета сравнивая списки файлов в каталоге и ini/ltr-файле
    if lists_matched(files, expected_files, information_files_list[0]) is False:
        raise Exception("нецелостность пакета {}".format(folder_path))
    return True


def process_exception(error, folder, config, traceback):
    # ошибки в консоль, общий лог, ERRORS.txt, email
    print("Ошибка на пакете {}".format(folder))
    print(error)
    message = "Ошибка на пакете {} \n{} \n{}".format(folder, error, traceback)
    logging.error(message)
    if not config["mail"] is None:
        send_email(config["mail"]["from"],
                   config["mail"]["to"],
                   config["mail"]["server"],
                   message)


def do_backup(folder, backup_path):
    today = datetime.now().strftime(DATE_FORMAT)
    folder_name = os.path.split(folder)[1]
    backup_full_path = os.path.join(backup_path, today)
    backup_full_path = os.path.join(backup_full_path, folder_name)
    if not os.path.exists(backup_full_path):
        os.makedirs(backup_full_path)

    for item in os.listdir(folder):
        logging.debug("Выполнение бэкапа файла {}".format(item))
        s = os.path.join(folder, item)
        d = os.path.join(backup_full_path, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, False, None)
        else:
            shutil.copy2(s, d)


def move_folder(source, destination):
    folder_name = os.path.split(source)[1]
    backup_full_path = os.path.join(destination, folder_name)
    shutil.move(source, backup_full_path)


def process_folder(folder, config):
    if config["backup_path"]:
        try:
            logging.debug("Выполнение бэкапа")
            do_backup(folder, config["backup_path"])
        except:
            raise Exception("Не удалось сделать бекап папки {}".format(folder))
    try:
        logging.debug("Перемещение пакета")
        move_folder(folder, config["destination_path"])
    except:
        raise Exception("Не удалось переместить папку {}".format(folder))


def process_pockets(source_folders_list, config):
    for folder in source_folders_list:
        try:
            logging.info("Обработка пакета {}".format(folder))
            if is_pocket_valid(folder) is True:
                logging.debug("Пакет прошел валидацию")
                process_folder(folder, config)
                logging.info("Успешно")
            else:
                continue
        except Exception as err:
            logging.debug("перехват")
            process_exception(err, folder, config, traceback.format_exc())
            write_main_error_to_file(traceback.format_exc())
            continue


def main():
    logging.debug("Старт")
    config = get_config()
    config_folders_check(config["source_path"], config["destination_path"], config["backup_path"])
    source_folders = get_source_folders_list(config["source_path"])
    if not source_folders is None:
        logging.debug("Найдено пакетов {}".format(len(source_folders)))
        process_pockets(source_folders, config)
    else:
        logging.debug("Найдено пакетов 0")


if __name__ == "__main__":
    try:
        main()
    except:
        # все необработанные ошибки записываются в файл ERRORS.txt и консоль
        write_main_error_to_file(traceback.format_exc())
        traceback.print_exc()