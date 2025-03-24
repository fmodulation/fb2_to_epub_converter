import os
import shutil
import logging
import re
from ebooklib import epub
from bs4 import BeautifulSoup, Tag
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FB2toEPUBConverter:
    def __init__(self, source_dir, target_dir=None):
        self.source_dir = Path(source_dir)
        self.base_folder = self.source_dir.name
        self.target_dir = Path(target_dir) if target_dir else Path.home() / 'Documents' / 'Converted_Books'
        self.target_dir = self.target_dir / self.base_folder
        self.target_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f'Инициализирован конвертер. Исходная папка: {self.source_dir}, Целевая папка: {self.target_dir}')

    def extract_author_from_filename(self, filename):
        # Регулярное выражение для очистки имени автора от цифр и спецсимволов
        author_part = filename.split('-')[0].strip()
        cleaned_author = re.sub(r'[^а-яА-ЯёЁa-zA-Z\s]', '', author_part)
        return cleaned_author if cleaned_author else 'Unknown'

    def convert_fb2_to_epub(self, fb2_path, epub_path):
        try:
            logging.info(f'Начинаю конвертацию: {fb2_path}')
            with open(fb2_path, 'r', encoding='utf-8') as fb2_file:
                fb2_content = fb2_file.read()

            soup = BeautifulSoup(fb2_content, 'xml')

            # Логируем все элементы с пространством имен
            for tag in soup.find_all(lambda t: t.has_attr('l:href') or t.has_attr('xlink:href')):
                logging.warning(f'Найден элемент с href: {tag.name} {tag.attrs}')

            # Обработка всех элементов с l:href или xlink:href
            for tag in soup.find_all(attrs={"l:href": True}):
                if isinstance(tag, Tag):
                    href = tag['l:href']
                    del tag['l:href']
                    tag['href'] = href  # Убираем префикс l:

            for tag in soup.find_all(attrs={"xlink:href": True}):
                if isinstance(tag, Tag):
                    href = tag['xlink:href']
                    del tag['xlink:href']
                    tag['href'] = href  # Убираем префикс xlink

            # Создаем книгу
            book = epub.EpubBook()
            title = soup.find('book-title').text if soup.find('book-title') else 'Untitled'
            book.set_title(title)
            book.set_language('ru')

            # Обработка автора
            author = soup.find('author')
            if author:
                first_name = author.find('first-name').text if author.find('first-name') else ''
                last_name = author.find('last-name').text if author.find('last-name') else ''
                author_name = f"{first_name} {last_name}".strip()
            else:
                author_name = self.extract_author_from_filename(fb2_path.stem)
            book.add_author(author_name)

            # Обработка пространств имен и изображений
            body_content = []
            images = {}
            # В методе convert_fb2_to_epub:
            for binary in soup.find_all('binary', id=True):
                if binary.get('content-type', '').startswith('image/'):
                    img_id = binary['id']
                    img_data = binary.text.encode('utf-8')
                    img = epub.EpubImage(
                        uid=img_id,
                        file_name=f"images/{img_id}.jpg",
                        media_type=binary['content-type'],
                        content=img_data
                    )
                    book.add_item(img)

            for section in soup.find_all('section'):
                for element in section.children:
                    if isinstance(element, Tag):
                        # Обработка изображений
                        if element.name == 'image' and element.get('href'):
                            img_id = element['href'].replace('#', '')
                            if img_id in images:
                                img = epub.EpubImage()
                                img.file_name = f"images/{img_id}.jpg"
                                img.media_type = 'image/jpeg'
                                img.content = images[img_id]
                                book.add_item(img)
                                element.name = 'img'
                                element['src'] = img.file_name
                                del element['href']
                        body_content.append(str(element))

            # Создаем HTML-страницу с корректными пространствами имен
            content = epub.EpubHtml(
                title='Content',
                file_name='content.xhtml',
                lang='ru',
                content=(
                    '<html xmlns="http://www.w3.org/1999/xhtml" '
                    'xmlns:epub="http://www.idpf.org/2007/ops">'
                    '<head><title>{title}</title></head>'
                    '<body>{body}</body></html>'.format(
                        title=title,
                        body=''.join(body_content)
                    )
                )
            )
            book.add_item(content)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ['nav', content]

            # Добавляем изображения в книгу
            for img in soup.find_all('image'):
                if 'href' in img.attrs:
                    img_path = fb2_path.parent / img['href']
                    if img_path.exists():
                        img_item = epub.EpubImage()
                        img_item.file_name = img['href']
                        img_item.content = img_path.read_bytes()
                        book.add_item(img_item)

            # Сохраняем книгу
            epub.write_epub(epub_path, book, {})
            logging.info(f'Успешно конвертирован: {fb2_path} -> {epub_path}')

        except Exception as e:
            logging.error(f'Ошибка при конвертации {fb2_path}: {e}')
            # Логируем содержимое проблемного элемента
            if 'l:href' in str(e):
                logging.error(f'Проблемный элемент: {e.element}')

    def process_folder(self):
        logging.info('Начинаю обработку папок...')
        for root, _, files in os.walk(self.source_dir):
            rel_path = Path(root).relative_to(self.source_dir)
            target_path = self.target_dir / rel_path
            target_path.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = Path(root) / file
                try:
                    if file.endswith('.fb2'):
                        epub_file = target_path / f"{src_file.stem}.epub"
                        self.convert_fb2_to_epub(src_file, epub_file)
                    elif file.endswith('.epub'):
                        dst_file = target_path / file
                        shutil.copy2(src_file, dst_file)
                        logging.info(f'Скопирован: {src_file} -> {dst_file}')
                except Exception as e:
                    logging.error(f'Ошибка при обработке файла {src_file}: {e}')
                    # Логируем содержимое файла
                    if src_file.exists():
                        with open(src_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            logging.error(f'Содержимое файла {src_file}:\n{content[:500]}...')
        logging.info('Обработка папок завершена.')

if __name__ == "__main__":
    source_directory = '/Volumes/homes/fmodulation/Personal/Книги/warhammer 40k/Хороший перевод/Войны инквизиции'
    converter = FB2toEPUBConverter(source_directory)
    converter.process_folder()
