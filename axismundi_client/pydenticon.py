# This module originated here https://github.com/azaghal/pydenticon
# For digest operations.
import hashlib

# For saving the images from Pillow.
from io import BytesIO

# Pillow for Image processing.
from PIL import Image, ImageDraw

# For decoding hex values (works both for Python 2.7.x and Python 3.x).
import binascii


class Generator(object):

    def __init__(self, rows, columns, digest=hashlib.md5, foreground=["#000000"], background="#ffffff"):

        entropy_provided = len(digest(b"test").hexdigest()) // 2 * 8
        entropy_required = (columns // 2 + columns % 2) * rows + 8

        if entropy_provided < entropy_required:
            raise ValueError("Passed digest '%s' is not capable of providing %d bits of entropy" % (str(digest), entropy_required))

        # Set the expected digest size. This is used later on to detect if
        # passed data is a digest already or not.
        self.digest_entropy = entropy_provided

        self.rows = rows
        self.columns = columns

        self.foreground = foreground
        self.background = background

        self.digest = digest

    def _get_bit(self, n, hash_bytes):

        if hash_bytes[n // 8] >> int(8 - ((n % 8) + 1)) & 1 == 1:
            return True

        return False

    def _generate_matrix(self, hash_bytes):

        half_columns = self.columns // 2 + self.columns % 2
        cells = self.rows * half_columns

        # Initialise the matrix (list of rows) that will be returned.
        matrix = [[False] * self.columns for _ in range(self.rows)]

        # Process the cells one by one.
        for cell in range(cells):

            if self._get_bit(cell, hash_bytes[1:]):

                # Determine the cell coordinates in matrix.
                column = cell // self.columns
                row = cell % self.rows

                # Mark the cell and its reflection. Central column may get
                # marked twice, but we don't care.
                matrix[row][column] = True
                matrix[row][self.columns - column - 1] = True

        return matrix

    def _data_to_digest_byte_list(self, data):

        # If data seems to provide identical amount of entropy as digest, it
        # could be a hex digest already.
        if len(data) // 2 == self.digest_entropy // 8:
            try:
                binascii.unhexlify(data.encode('utf-8'))
                digest = data.encode('utf-8')
            # Handle Python 2.x exception.
            except (TypeError):
                digest = self.digest(data.encode('utf-8')).hexdigest()
            # Handle Python 3.x exception.
            except (binascii.Error):
                digest = self.digest(data.encode('utf-8')).hexdigest()
        else:
            digest = self.digest(data.encode('utf-8')).hexdigest()

        return [int(digest[i * 2:i * 2 + 2], 16) for i in range(16)]

    def _generate_png(self, matrix, width, height, padding, foreground, background):

        # Set-up a new image object, setting the background to provided value.
        image = Image.new("RGBA", (width + padding[2] + padding[3], height + padding[0] + padding[1]), background)

        # Set-up a draw image (for drawing the blocks).
        draw = ImageDraw.Draw(image)

        # Calculate the block widht and height.
        block_width = width // self.columns
        block_height = height // self.rows

        # Go through all the elements of a matrix, and draw the rectangles.
        for row, row_columns in enumerate(matrix):
            for column, cell in enumerate(row_columns):
                if cell:
                    # Set-up the coordinates for a block.
                    x1 = padding[2] + column * block_width
                    y1 = padding[0] + row * block_height
                    x2 = padding[2] + (column + 1) * block_width - 1
                    y2 = padding[0] + (row + 1) * block_height - 1

                    # Draw the rectangle.
                    draw.rectangle((x1, y1, x2, y2), fill=foreground)

        # Set-up a stream where image will be saved.
        stream = BytesIO()

        # Save the image to stream.
        image.save(stream, format="png", optimize=True)
        image_raw = stream.getvalue()
        stream.close()

        # Return the resulting PNG.
        return image_raw

    def generate(self, data, width, height, padding=(0, 0, 0, 0), output_format="png", inverted=False):

        # Calculate the digest, and get byte list.
        digest_byte_list = self._data_to_digest_byte_list(data)

        # Create the matrix describing which block should be filled-in.
        matrix = self._generate_matrix(digest_byte_list)

        # Determine the background and foreground colours.
        if output_format == "png":
            background = self.background
            foreground = self.foreground[digest_byte_list[0] % len(self.foreground)]
        elif output_format == "ascii":
            foreground = "+"
            background = "-"

        # Swtich the colours if inverted image was requested.
        if inverted:
            foreground, background = background, foreground

        # Generate the identicon in requested format.
        if output_format == "png":
            return self._generate_png(matrix, width, height, padding, foreground, background)
        if output_format == "ascii":
            return self._generate_ascii(matrix, foreground, background)
        else:
            raise ValueError("Unsupported format requested: %s" % output_format)
