package org.example;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;
import java.io.StringReader;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;


public class MonthlyCount {

    public static class MonthlyMapper
            extends Mapper<LongWritable, Text, Text, LongWritable> {

        private final Text outKey = new Text();
        private final LongWritable outValue = new LongWritable(1);

        @Override
        protected void map(LongWritable key,
                           Text value,
                           Context context)
                throws IOException, InterruptedException {

            String line = value.toString();


            if (line.startsWith("Date received,")) {
                return;
            }

            try {

                CSVParser parser = CSVParser.parse(
                        new StringReader(line),
                        CSVFormat.DEFAULT
                );

                for (CSVRecord record : parser) {


                    if (record.size() == 0) {
                        return;
                    }

                    String date = record.get(0).trim();


                    LocalDate parsedDate = LocalDate.parse(date);


                    String month = parsedDate.toString().substring(0, 7);

                    outKey.set(month);


                    context.write(outKey, outValue);
                }

                parser.close();

            } catch (DateTimeParseException e) {

                context.getCounter(
                        "MonthlyCount",
                        "INVALID_DATE"
                ).increment(1);

            } catch (Exception e) {

                context.getCounter(
                        "MonthlyCount",
                        "INVALID_CSV"
                ).increment(1);
            }
        }
    }

    // ==================== Reducer ====================
    public static class MonthlyReducer
            extends Reducer<Text, LongWritable, Text, LongWritable> {

        private final LongWritable result = new LongWritable();

        @Override
        protected void reduce(Text key,
                              Iterable<LongWritable> values,
                              Context context)
                throws IOException, InterruptedException {

            long sum = 0;

            // 累加每个月的投诉数量
            for (LongWritable value : values) {
                sum += value.get();
            }

            result.set(sum);

            context.write(key, result);
        }
    }

    // ==================== Driver ====================
    public static void main(String[] args) throws Exception {

        if (args.length != 2) {
            System.err.println(
                    "用法：MonthlyCount <输入路径> <输出路径>"
            );
            System.exit(2);
        }


        Configuration conf = new Configuration();


        Job job = Job.getInstance(
                conf,
                "CFPB Monthly Complaint Count"
        );


        job.setJarByClass(MonthlyCount.class);


        job.setMapperClass(MonthlyMapper.class);

        // 设置 Combiner
        job.setCombinerClass(MonthlyReducer.class);

        // 设置 Reducer
        job.setReducerClass(MonthlyReducer.class);

        // 设置 Mapper 输出类型
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);

        // 设置最终输出类型
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);

        // 设置一个 Reducer
        job.setNumReduceTasks(1);

        // 设置输入路径
        FileInputFormat.addInputPath(
                job,
                new Path(args[0])
        );

        // 设置输出路径
        FileOutputFormat.setOutputPath(
                job,
                new Path(args[1])
        );

        // 提交任务
        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
