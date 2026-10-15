	.file	"test_assembly.c"
	.text
	.align	4
	.global	convert_sample_arith
	.type	convert_sample_arith, @function
convert_sample_arith:
	entry	sp, 32
	srai	a2, a2, 8
	retw.n
	.size	convert_sample_arith, .-convert_sample_arith
	.align	4
	.global	convert_buffer
	.type	convert_buffer, @function
convert_buffer:
	entry	sp, 32
	beqz.n	a4, .L3
	slli	a8, a4, 2
	addi	a8, a8, -4
	srli	a8, a8, 2
	addi.n	a8, a8, 1
	loop	a8, .L5_LEND
.L5:
	l32i.n	a9, a3, 0
	addi.n	a3, a3, 4
	srai	a9, a9, 8
	s32i.n	a9, a2, 0
	addi.n	a2, a2, 4
	.L5_LEND:
.L3:
	retw.n
	.size	convert_buffer, .-convert_buffer
	.align	4
	.global	convert_buffer_inplace
	.type	convert_buffer_inplace, @function
convert_buffer_inplace:
	entry	sp, 32
	beqz.n	a3, .L11
	slli	a8, a3, 2
	addi	a8, a8, -4
	srli	a8, a8, 2
	addi.n	a8, a8, 1
	loop	a8, .L13_LEND
.L13:
	l32i.n	a9, a2, 0
	srai	a9, a9, 8
	s32i.n	a9, a2, 0
	addi.n	a2, a2, 4
	.L13_LEND:
.L11:
	retw.n
	.size	convert_buffer_inplace, .-convert_buffer_inplace
	.ident	"GCC: (crosstool-NG esp-15.2.0_20251204) 15.2.0"
